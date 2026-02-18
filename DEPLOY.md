# Odoo-TopTex Proxy API

API proxy pour l'intégration entre Odoo et TopTex.

## Installation locale

```bash
# Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate  # Sur Windows: .venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos paramètres
```

## Lancer l'API localement

```bash
uvicorn main:app --reload
```

L'API sera disponible sur `http://localhost:8000`

## Documentation interactive

- Swagger UI : `http://localhost:8000/docs`
- ReDoc : `http://localhost:8000/redoc`

## Déploiement sur Render

### 1. Créer un compte Render
Allez sur [render.com](https://render.com) et créez un compte.

### 2. Configuration sur Render

1. Cliquez sur **"New +"** et sélectionnez **"Web Service"**
2. Connectez votre repository GitHub
3. Sélectionnez ce repository
4. Configurez les paramètres :
   - **Name** : `odoo-toptex-proxy`
   - **Environment** : `Python 3`
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `uvicorn main:app --host 0.0.0.0 --port $PORT`

### 3. Ajouter les variables d'environnement

Allez dans l'onglet **"Environment"** et ajoutez :

```
TOPTEX_API_KEY=your_api_key_here
TOPTEX_BASE_URL=https://api.toptex.io/v3
WEBHOOK_SECRET=your_webhook_secret_here
```

### 4. Déployer

Cliquez sur **"Create Web Service"**. Render déploiera automatiquement votre API.

## Endpoints disponibles

### Authentification
- `GET /auth` - Vérifier l'état de l'authentification TopTex (retourne le token et sa date d'expiration)

**Fonctionnement automatique** : L'API s'authentifie automatiquement auprès de TopTex via l'endpoint `/authenticate` au démarrage et met en cache le token. Le token est automatiquement rafraîchi quand nécessaire.

### Produits
- `GET /products` - Lister tous les produits
- `GET /products/{sku}` - Détail d'un produit
- `POST /products` - Créer un produit
- `PUT /products/{sku}` - Modifier un produit
- `DELETE /products/{sku}` - Supprimer un produit

### Commandes
- `GET /orders` - Lister les commandes
- `GET /orders/{order_number}` - Détail d'une commande
- `POST /orders` - Créer une commande
- `PUT /orders/{order_number}` - Mettre à jour une commande
- `DELETE /orders/{order_number}` - Annuler une commande

### Clients
- `GET /customers` - Lister les clients
- `GET /customers/{customer_id}` - Détail d'un client
- `POST /customers` - Créer un client
- `PUT /customers/{customer_id}` - Modifier un client
- `DELETE /customers/{customer_id}` - Supprimer un client

### Webhook Odoo
- `POST /odoo` - Recevoir et traiter les webhooks Odoo

### Utilitaires
- `GET /auth` - Vérifier l'état de l'authentification TopTex
- `GET /health` - Vérifier la connexion à TopTex
- `GET /` - Info sur l'API

## Webhook Odoo

Pour intégrer avec Odoo, configurez un webhook qui envoie les données à :
```
https://your-app.onrender.com/odoo
```

**Headers requis** :
```
x-odoo-signature: your_webhook_secret_here
Content-Type: application/json
```

**Payload exemple** :
```json
{
  "type": "order_created",
  "order_number": "ORD-001",
  "customer_id": "CUST-001",
  "items": [{"sku": "SKU-001", "qty": 1, "price": 99.99}],
  "total_price": 99.99,
  "shipping_address": {...}
}
```

## Support

Pour plus de détails, consultez la documentation Render : [render.com/docs](https://render.com/docs)
