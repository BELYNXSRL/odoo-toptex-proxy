from fastapi import FastAPI, Request, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import os
import requests
import logging
import time
from functools import wraps
from datetime import datetime, timedelta

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Odoo-TopTex Proxy", version="1.0.0")

TOPTEX_API_KEY = os.getenv("TOPTEX_API_KEY")
TOPTEX_BASE_URL = os.getenv("TOPTEX_BASE_URL", "https://api.toptex.io/v3")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# =============================================================================
# Gestion de l'authentification TopTex
# =============================================================================

class AuthenticationManager:
    """Gestionnaire d'authentification avec cache du token"""
    def __init__(self):
        self.token = None
        self.token_expiry = None
    
    def is_token_valid(self) -> bool:
        """Vérifie si le token est valide et non expiré"""
        if self.token is None or self.token_expiry is None:
            return False
        return datetime.now() < self.token_expiry
    
    def authenticate(self) -> str:
        """S'authentifie auprès de TopTex et retourne le token"""
        try:
            logger.info("🔐 Authentification auprès de TopTex...")
            response = requests.post(
                f"{TOPTEX_BASE_URL}/authenticate",
                json={"api_key": TOPTEX_API_KEY},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            self.token = data.get("token")
            # Assume le token expire dans 24h (à adapter selon la doc TopTex)
            self.token_expiry = datetime.now() + timedelta(hours=24)
            
            logger.info(f"✓ Authentification réussie. Token valide jusqu'à {self.token_expiry}")
            return self.token
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Erreur d'authentification: {str(e)}")
            raise HTTPException(status_code=503, detail=f"Authentication failed: {str(e)}")
    
    def get_token(self) -> str:
        """Retourne un token valide, en authentifiant si nécessaire"""
        if not self.is_token_valid():
            return self.authenticate()
        return self.token

# Instance globale du gestionnaire d'authentification
auth_manager = AuthenticationManager()

# =============================================================================
# Models Pydantic
# =============================================================================

class Product(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    price: float
    stock: int
    category: Optional[str] = None

class Order(BaseModel):
    order_number: str
    customer_id: str
    items: List[dict]
    total_price: float
    shipping_address: Optional[dict] = None
    status: Optional[str] = "pending"

class Customer(BaseModel):
    customer_id: str
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[dict] = None

class UpdateOrder(BaseModel):
    status: Optional[str] = None
    tracking_number: Optional[str] = None

# =============================================================================
# Utilitaires et Middleware
# =============================================================================

def retry_with_backoff(max_retries=3, backoff_factor=1):
    """Décorateur pour réessayer les requêtes avec backoff exponentiel"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    if attempt == max_retries - 1:
                        raise
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(f"Tentative {attempt + 1} échouée. Attente {wait_time}s avant nouvelle tentative")
                    time.sleep(wait_time)
        return wrapper
    return decorator

def get_toptex_headers():
    """Retourne les headers nécessaires pour les requêtes TopTex avec token d'authentification"""
    token = auth_manager.get_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

def verify_webhook_secret(req: Request):
    """Vérifie le secret du webhook"""
    if WEBHOOK_SECRET:
        if req.headers.get("x-odoo-signature") != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized")

# =============================================================================
# PRODUITS - Endpoints
# =============================================================================

@app.get("/products")
@retry_with_backoff()
async def get_products(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500)):
    """Récupère la liste de tous les produits TopTex"""
    try:
        headers = get_toptex_headers()
        response = requests.get(
            f"{TOPTEX_BASE_URL}/products",
            headers=headers,
            params={"skip": skip, "limit": limit},
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Produits récupérés avec succès (skip={skip}, limit={limit})")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la récupération des produits: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.get("/products/{sku}")
@retry_with_backoff()
async def get_product(sku: str):
    """Récupère les détails d'un produit spécifique"""
    try:
        headers = get_toptex_headers()
        response = requests.get(
            f"{TOPTEX_BASE_URL}/products/{sku}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Produit {sku} récupéré")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la récupération du produit {sku}: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.post("/products")
@retry_with_backoff()
async def create_product(product: Product):
    """Crée un nouveau produit dans TopTex"""
    try:
        headers = get_toptex_headers()
        response = requests.post(
            f"{TOPTEX_BASE_URL}/products",
            headers=headers,
            json=product.dict(),
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Produit {product.sku} créé")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la création du produit: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.put("/products/{sku}")
@retry_with_backoff()
async def update_product(sku: str, product: Product):
    """Met à jour un produit existant"""
    try:
        headers = get_toptex_headers()
        response = requests.put(
            f"{TOPTEX_BASE_URL}/products/{sku}",
            headers=headers,
            json=product.dict(),
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Produit {sku} mis à jour")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la mise à jour du produit {sku}: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.delete("/products/{sku}")
@retry_with_backoff()
async def delete_product(sku: str):
    """Supprime un produit"""
    try:
        headers = get_toptex_headers()
        response = requests.delete(
            f"{TOPTEX_BASE_URL}/products/{sku}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Produit {sku} supprimé")
        return {"message": "Product deleted successfully"}
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la suppression du produit {sku}: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

# =============================================================================
# COMMANDES - Endpoints
# =============================================================================

@app.get("/orders")
@retry_with_backoff()
async def get_orders(status: Optional[str] = None, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500)):
    """Récupère la liste de toutes les commandes"""
    try:
        headers = get_toptex_headers()
        params = {"skip": skip, "limit": limit}
        if status:
            params["status"] = status
        response = requests.get(
            f"{TOPTEX_BASE_URL}/orders",
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Commandes récupérées (status={status}, skip={skip}, limit={limit})")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la récupération des commandes: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.get("/orders/{order_number}")
@retry_with_backoff()
async def get_order(order_number: str):
    """Récupère les détails d'une commande spécifique"""
    try:
        headers = get_toptex_headers()
        response = requests.get(
            f"{TOPTEX_BASE_URL}/orders/{order_number}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Commande {order_number} récupérée")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la récupération de la commande {order_number}: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.post("/orders")
@retry_with_backoff()
async def create_order(order: Order):
    """Crée une nouvelle commande dans TopTex"""
    try:
        headers = get_toptex_headers()
        response = requests.post(
            f"{TOPTEX_BASE_URL}/orders",
            headers=headers,
            json=order.dict(),
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Commande {order.order_number} créée")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la création de la commande: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.put("/orders/{order_number}")
@retry_with_backoff()
async def update_order(order_number: str, update: UpdateOrder):
    """Met à jour le statut ou les infos de suivi d'une commande"""
    try:
        headers = get_toptex_headers()
        response = requests.put(
            f"{TOPTEX_BASE_URL}/orders/{order_number}",
            headers=headers,
            json=update.dict(exclude_unset=True),
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Commande {order_number} mise à jour")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la mise à jour de la commande {order_number}: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.delete("/orders/{order_number}")
@retry_with_backoff()
async def delete_order(order_number: str):
    """Annule/supprime une commande"""
    try:
        headers = get_toptex_headers()
        response = requests.delete(
            f"{TOPTEX_BASE_URL}/orders/{order_number}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Commande {order_number} supprimée")
        return {"message": "Order cancelled successfully"}
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la suppression de la commande {order_number}: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

# =============================================================================
# CLIENTS - Endpoints
# =============================================================================

@app.get("/customers")
@retry_with_backoff()
async def get_customers(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500)):
    """Récupère la liste de tous les clients"""
    try:
        headers = get_toptex_headers()
        response = requests.get(
            f"{TOPTEX_BASE_URL}/customers",
            headers=headers,
            params={"skip": skip, "limit": limit},
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Clients récupérés (skip={skip}, limit={limit})")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la récupération des clients: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.get("/customers/{customer_id}")
@retry_with_backoff()
async def get_customer(customer_id: str):
    """Récupère les détails d'un client spécifique"""
    try:
        headers = get_toptex_headers()
        response = requests.get(
            f"{TOPTEX_BASE_URL}/customers/{customer_id}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Client {customer_id} récupéré")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la récupération du client {customer_id}: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.post("/customers")
@retry_with_backoff()
async def create_customer(customer: Customer):
    """Crée un nouveau client dans TopTex"""
    try:
        headers = get_toptex_headers()
        response = requests.post(
            f"{TOPTEX_BASE_URL}/customers",
            headers=headers,
            json=customer.dict(),
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Client {customer.customer_id} créé")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la création du client: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.put("/customers/{customer_id}")
@retry_with_backoff()
async def update_customer(customer_id: str, customer: Customer):
    """Met à jour un client existant"""
    try:
        headers = get_toptex_headers()
        response = requests.put(
            f"{TOPTEX_BASE_URL}/customers/{customer_id}",
            headers=headers,
            json=customer.dict(),
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Client {customer_id} mis à jour")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la mise à jour du client {customer_id}: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

@app.delete("/customers/{customer_id}")
@retry_with_backoff()
async def delete_customer(customer_id: str):
    """Supprime un client"""
    try:
        headers = get_toptex_headers()
        response = requests.delete(
            f"{TOPTEX_BASE_URL}/customers/{customer_id}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"✓ Client {customer_id} supprimé")
        return {"message": "Customer deleted successfully"}
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Erreur lors de la suppression du client {customer_id}: {str(e)}")
        raise HTTPException(status_code=503, detail=f"TopTex API error: {str(e)}")

# =============================================================================
# WEBHOOK ODOO - Endpoint
# =============================================================================

@app.post("/odoo")
async def from_odoo(req: Request):
    """Reçoit les webhooks d'Odoo et les traite"""
    verify_webhook_secret(req)
    
    try:
        payload = await req.json()
        logger.info(f"✓ Webhook Odoo reçu: {payload.get('type', 'unknown')}")
        
        # Traitement selon le type de webhook
        webhook_type = payload.get("type")
        
        if webhook_type == "order_created":
            # Créer la commande dans TopTex
            order = Order(
                order_number=payload.get("order_number"),
                customer_id=payload.get("customer_id"),
                items=payload.get("items", []),
                total_price=payload.get("total_price", 0),
                shipping_address=payload.get("shipping_address")
            )
            result = await create_order(order)
            return {"status": "processed", "result": result}
        
        elif webhook_type == "order_updated":
            # Mettre à jour la commande dans TopTex
            update = UpdateOrder(
                status=payload.get("status"),
                tracking_number=payload.get("tracking_number")
            )
            result = await update_order(payload.get("order_number"), update)
            return {"status": "processed", "result": result}
        
        else:
            logger.warning(f"Type de webhook inconnu: {webhook_type}")
            return {"status": "unknown_type", "webhook_type": webhook_type}
            
    except Exception as e:
        logger.error(f"✗ Erreur lors du traitement du webhook Odoo: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error processing webhook: {str(e)}")

# =============================================================================
# AUTHENTICATION - Endpoint
# =============================================================================

@app.get("/auth")
async def auth_status():
    """Vérifie l'état de l'authentification TopTex"""
    try:
        token = auth_manager.get_token()
        return {
            "status": "authenticated",
            "token_valid": auth_manager.is_token_valid(),
            "token_expiry": auth_manager.token_expiry.isoformat() if auth_manager.token_expiry else None
        }
    except Exception as e:
        logger.error(f"✗ Erreur d'authentification: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Authentication error: {str(e)}")

# =============================================================================
# HEALTH CHECK - Endpoint
# =============================================================================

@app.get("/health")
async def health_check():
    """Vérifie l'état de l'API"""
    try:
        headers = get_toptex_headers()
        response = requests.get(
            f"{TOPTEX_BASE_URL}/health",
            headers=headers,
            timeout=10
        )
        return {
            "status": "healthy",
            "toptex_api": "connected" if response.status_code == 200 else "disconnected"
        }
    except:
        return {
            "status": "degraded",
            "toptex_api": "disconnected"
        }

@app.get("/")
async def root():
    """Endpoint racine avec info sur l'API"""
    return {
        "name": "Odoo-TopTex Proxy",
        "version": "1.0.0",
        "description": "API proxy pour intégration Odoo <-> TopTex",
        "endpoints": {
            "products": "/products (GET, POST)",
            "orders": "/orders (GET, POST)",
            "customers": "/customers (GET, POST)",
            "webhooks": "/odoo (POST)",
            "authentication": "/auth (GET)",
            "health": "/health (GET)"
        }
    }

# =============================================================================
# STARTUP EVENT - Authentification automatique
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """S'authentifie automatiquement auprès de TopTex au démarrage"""
    try:
        token = auth_manager.get_token()
        logger.info("✓ API démarrée et authentifiée auprès de TopTex")
    except Exception as e:
        logger.warning(f"⚠ Attention: Impossible de s'authentifier au démarrage: {str(e)}")
        logger.info("  L'authentification sera tentée lors du premier appel API")
