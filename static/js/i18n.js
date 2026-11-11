(() => {
  'use strict';
  const STORAGE_KEY = 'smartstore-language';
  const pairs = [
    ['Smart Store', 'Smart Store'],
    ['Storage Overview', 'Vue d’ensemble du stockage'],
    ['Storage overview', 'Vue d’ensemble du stockage'],
    ['Sign out', 'Se déconnecter'],
    ['Notifications', 'Notifications'],
    ['View profile', 'Voir le profil'],
    ['Profile', 'Profil'],
    ['Switch to light mode', 'Passer au mode clair'],
    ['Switch to dark mode', 'Passer au mode sombre'],
    ['My account', 'Mon compte'],
    ['Self-checkout', 'Caisse libre-service'],
    ['Dashboard', 'Tableau de bord'],
    ['Storage History', 'Historique du stockage'],
    ['Inventory', 'Inventaire'],
    ['Scan Testing', 'Test de lecture RFID'],
    ['Users', 'Utilisateurs'],
    ['Settings', 'Paramètres'],
    ['Customers', 'Clients'],
    ['STORAGE MONITORING', 'SURVEILLANCE DU STOCKAGE'],
    ['Refrigerator readings update automatically every 3 seconds.', 'Les données des réfrigérateurs sont actualisées toutes les 3 secondes.'],
    ['Waiting for readings', 'En attente de données'],
    ['DATA AVAILABLE', 'DONNÉES DISPONIBLES'],
    ['Temperature', 'Température'],
    ['Humidity', 'Humidité'],
    ['Current threshold', 'Seuil actuel'],
    ['Fan status', 'État du ventilateur'],
    ['Not available', 'Non disponible'],
    ['Unknown', 'Inconnu'],
    ['No refrigerator readings yet. The cards will appear when the backend receives sensor data.', 'Aucune donnée de réfrigérateur pour le moment. Les cartes apparaîtront dès la réception de mesures.'],
    ['Temperature history', 'Historique de température'],
    ['Humidity history', 'Historique d’humidité'],
    ['All refrigerators', 'Tous les réfrigérateurs'],
    ['Temperature chart', 'Graphique de température'],
    ['Humidity chart', 'Graphique d’humidité'],
    ['Select refrigerator for temperature chart', 'Choisir un réfrigérateur pour le graphique de température'],
    ['Select refrigerator for humidity chart', 'Choisir un réfrigérateur pour le graphique d’humidité'],
    ['STOCK MANAGEMENT', 'GESTION DES STOCKS'],
    ['Manage products and monitor stock levels', 'Gérez les produits et surveillez les niveaux de stock'],
    ['Products', 'Produits'],
    ['All Products', 'Tous les produits'],
    ['+ Add product', '+ Ajouter un produit'],
    ['Add product', 'Ajouter un produit'],
    ['Add new product', 'Ajouter un produit'],
    ['Generate Report', 'Générer un rapport'],
    ['Search products...', 'Rechercher des produits...'],
    ['All categories', 'Toutes les catégories'],
    ['Category', 'Catégorie'],
    ['Name', 'Nom'],
    ['Company', 'Entreprise'],
    ['Price', 'Prix'],
    ['Stock', 'Stock'],
    ['Actions', 'Actions'],
    ['RFID tags', 'Étiquettes RFID'],
    ['RFID Tags', 'Étiquettes RFID'],
    ['Register EPC', 'Enregistrer un EPC'],
    ['Edit', 'Modifier'],
    ['Delete', 'Supprimer'],
    ['Delete this product?', 'Supprimer ce produit ?'],
    ['No products yet', 'Aucun produit pour le moment'],
    ['Add your first product to start managing inventory.', 'Ajoutez votre premier produit pour commencer à gérer votre inventaire.'],
    ['Receive stock', 'Réceptionner le stock'],
    ['Select a product', 'Choisir un produit'],
    ['Product', 'Produit'],
    ['Quantity received', 'Quantité reçue'],
    ['Supplier', 'Fournisseur'],
    ['Optional', 'Facultatif'],
    ['Add a product before receiving stock.', 'Ajoutez un produit avant de réceptionner du stock.'],
    ['Recent receptions', 'Réceptions récentes'],
    ['Date received', 'Date de réception'],
    ['No stock receptions recorded yet.', 'Aucune réception de stock enregistrée.'],
    ['Total Products', 'Total des produits'],
    ['Total Value', 'Valeur totale'],
    ['Low Stock', 'Stock faible'],
    ['Out of Stock', 'Rupture de stock'],
    ['Current Stock', 'Stock actuel'],
    ['Manufacturer', 'Fabricant'],
    ['Quantity', 'Quantité'],
    ['Search', 'Rechercher'],
    ['RFID TESTING', 'TEST RFID'],
    ['Check registered tags and their product information.', 'Vérifiez les étiquettes enregistrées et les informations sur les produits.'],
    ['Back to inventory', 'Retour à l’inventaire'],
    ['Live reader', 'Lecteur en direct'],
    ['Pause scanning', 'Suspendre la lecture'],
    ['Resume scanning', 'Reprendre la lecture'],
    ['Start scanning', 'Démarrer la lecture'],
    ['Stop scanning', 'Arrêter la lecture'],
    ['Connecting to reader…', 'Connexion au lecteur…'],
    ['Hold tags near the reader. Products appear below automatically as EPCs are read.', 'Placez les étiquettes près du lecteur. Les produits apparaîtront automatiquement lorsqu’un EPC est lu.'],
    ['Status', 'État'],
    ['Registered', 'Enregistré'],
    ['Unregistered', 'Non enregistré'],
    ['Connected', 'Connecté'],
    ['Disconnected', 'Déconnecté'],
    ['Scan items', 'Scanner les articles'],
    ['Scan products', 'Scanner les produits'],
    ['Scan Products', 'Scanner les produits'],
    ['Membership', 'Adhésion'],
    ['Membership card', 'Carte de membre'],
    ['Confirm membership', 'Confirmer l’adhésion'],
    ['Continue as guest', 'Continuer comme invité'],
    ['Guest', 'Invité'],
    ['Review', 'Vérification'],
    ['Review cart', 'Vérifier le panier'],
    ['Payment', 'Paiement'],
    ['Payment Simulation', 'Simulation de paiement'],
    ['Demo only', 'Démonstration seulement'],
    ['Shopping list', 'Liste d’achats'],
    ['Shopping List', 'Liste d’achats'],
    ['Order Summary', 'Récapitulatif de commande'],
    ['Cart', 'Panier'],
    ['Your cart', 'Votre panier'],
    ['Your cart is empty', 'Votre panier est vide'],
    ['No items scanned yet', 'Aucun article scanné'],
    ['Product barcode', 'Code-barres du produit'],
    ['Add item', 'Ajouter un article'],
    ['Scan a barcode with your barcode scanner, or enter it and press Enter.', 'Scannez un code-barres ou saisissez-le, puis appuyez sur Entrée.'],
    ['Ready to scan.', 'Prêt à scanner.'],
    ['Clear cart', 'Vider le panier'],
    ['Remove', 'Retirer'],
    ['Subtotal', 'Sous-total'],
    ['Total', 'Total'],
    ['Total to pay', 'Total à payer'],
    ['Tax', 'Taxes'],
    ['Proceed to payment', 'Passer au paiement'],
    ['Continue to membership', 'Passer à l’adhésion'],
    ['Continue to review', 'Passer à la vérification'],
    ['Confirm order', 'Confirmer la commande'],
    ['Confirm Payment', 'Confirmer le paiement'],
    ['Complete checkout', 'Finaliser l’achat'],
    ['Credit card', 'Carte de crédit'],
    ['Debit card', 'Carte de débit'],
    ['Cash', 'Espèces'],
    ['Mobile wallet', 'Portefeuille mobile'],
    ['Test Visa', 'Visa de démonstration'],
    ['Demo terminal', 'Terminal de démonstration'],
    ['Change calculator', 'Calculateur de monnaie'],
    ['Contactless payment', 'Paiement sans contact'],
    ['Cash received (CAD)', 'Montant reçu (CAD)'],
    ['Change due', 'Monnaie à rendre'],
    ['Simulated PIN verification', 'Vérification du NIP simulée'],
    ['Simulated contactless payment', 'Paiement sans contact simulé'],
    ['No real payment credentials are required.', 'Aucune information bancaire réelle n’est nécessaire.'],
    ['I confirm my shopping list is correct.', 'Je confirme que ma liste d’achats est exacte.'],
    ['Payment successful', 'Paiement réussi'],
    ['Payment failed', 'Échec du paiement'],
    ['Payment method', 'Mode de paiement'],
    ['Receipt', 'Reçu'],
    ['Download receipt', 'Télécharger le reçu'],
    ['Email receipt', 'Envoyer le reçu par courriel'],
    ['Send receipt', 'Envoyer le reçu'],
    ['Points earned', 'Points gagnés'],
    ['Loyalty points', 'Points de fidélité'],
    ['CUSTOMER ACCOUNT', 'COMPTE CLIENT'],
    ['Your membership, loyalty points and purchase history.', 'Votre adhésion, vos points de fidélité et votre historique d’achats.'],
    ['Go to self-checkout', 'Accéder à la caisse libre-service'],
    ['Membership number:', 'Numéro de membre :'],
    ['Loyalty points:', 'Points de fidélité :'],
    ['Email:', 'Courriel :'],
    ['Phone:', 'Téléphone :'],
    ['Address:', 'Adresse :'],
    ['No email on file', 'Aucun courriel enregistré'],
    ['No phone on file', 'Aucun téléphone enregistré'],
    ['Purchase history', 'Historique des achats'],
    ['Date', 'Date'],
    ['No purchases yet', 'Aucun achat pour le moment'],
    ['Your receipts will appear here after your first checkout.', 'Vos reçus apparaîtront ici après votre premier achat.'],
    ['Add Customer', 'Ajouter un client'],
    ['View and Manage Customers', 'Consultez et gérez les clients'],
    ['No email', 'Aucun courriel'],
    ['No phone', 'Aucun téléphone'],
    ['No customers yet.', 'Aucun client pour le moment.'],
    ['Register Customer', 'Inscrire un client'],
    ['Back to customers', 'Retour aux clients'],
    ['Add a new customer to Smart Store', 'Ajouter un nouveau client à Smart Store'],
    ['First name', 'Prénom'],
    ['Last name', 'Nom de famille'],
    ['Address', 'Adresse'],
    ['Phone', 'Téléphone'],
    ['Email', 'Courriel'],
    ['Phone (optional)', 'Téléphone (facultatif)'],
    ['Email (optional)', 'Courriel (facultatif)'],
    ['Save', 'Enregistrer'],
    ['Save changes', 'Enregistrer les modifications'],
    ['Cancel', 'Annuler'],
    ['Back', 'Retour'],
    ['Confirm', 'Confirmer'],
    ['Close', 'Fermer'],
    ['Loading...', 'Chargement...'],
    ['Error', 'Erreur'],
    ['Success', 'Succès'],
    ['Update', 'Mettre à jour'],
    ['Refresh', 'Actualiser'],
    ['Details', 'Détails'],
    ['History', 'Historique'],
    ['Storage history', 'Historique du stockage'],
    ['Search by name', 'Rechercher par nom'],
    ['All', 'Tous'],
    ['Active', 'Actif'],
    ['Inactive', 'Inactif'],
    ['Available', 'Disponible'],
    ['Unavailable', 'Indisponible'],
    ['Sign in', 'Se connecter'],
    ['Log in', 'Se connecter'],
    ['Log out', 'Se déconnecter'],
    ['Create account', 'Créer un compte'],
    ['Password', 'Mot de passe'],
    ['Confirm password', 'Confirmer le mot de passe'],
    ['Forgot password?', 'Mot de passe oublié ?'],
    ['Welcome back', 'Bon retour'],
    ['Account', 'Compte'],
    ['Sign up', 'S’inscrire'],
    ['New product', 'Nouveau produit'],
    ['Edit product', 'Modifier le produit'],
    ['Product details', 'Détails du produit'],
    ['Search customers...', 'Rechercher des clients...'],
    ['Select category', 'Choisir une catégorie'],
    ['No results found', 'Aucun résultat trouvé'],
    ['Total stock', 'Stock total'],
    ['Total inventory value', 'Valeur totale de l’inventaire'],
    ['Recent activity', 'Activité récente'],
    ['No data available', 'Aucune donnée disponible'],
    ['No data', 'Aucune donnée'],
    ['Today', 'Aujourd’hui'],
    ['Yesterday', 'Hier'],
    ['Online', 'En ligne'],
    ['Offline', 'Hors ligne'],
    ['Never', 'Jamais']
  ];
  const dictionary = new Map(pairs);
  const reverse = new Map(pairs.map(([en, fr]) => [fr, en]));
  const origin = new WeakMap();
  let lang = localStorage.getItem(STORAGE_KEY) === 'fr' ? 'fr' : 'en';
  const skipParents = 'script,style,code,pre,textarea,[contenteditable="true"],[data-i18n-ignore]';

  function englishVersion(value) {
    if (dictionary.has(value)) return value;
    if (reverse.has(value)) return reverse.get(value);
    // Limited dynamic UI counters; never translate unknown user values.
    if (/^\d+ total$/.test(value)) return value;
    if (/^\d+ registered$/.test(value)) return value;
    if (/^Total:\s*\$/.test(value)) return value;
    if (/^Hello,\s+.+/.test(value)) return value;
    return null;
  }

  function translated(value) {
    if (dictionary.has(value)) return dictionary.get(value);
    if (/^(\d+) total$/.test(value)) return value.replace(/^(\d+) total$/, '$1 au total');
    if (/^(\d+) registered$/.test(value)) return value.replace(/^(\d+) registered$/, '$1 enregistrés');
    if (/^Total:\s*\$/.test(value)) return value.replace(/^Total:/, 'Total :');
    if (/^Hello,\s+/.test(value)) return value.replace(/^Hello,\s+/, 'Bonjour, ');
    return value;
  }

  function applyText(node) {
    const parent = node.parentElement;
    if (!parent || parent.closest(skipParents)) return;
    const current = node.nodeValue;
    const trimmed = current.trim();
    if (!trimmed) return;
    const known = origin.get(node);
    let english;
    if (known !== undefined && (current === known || current === translated(known))) {
      english = known;
    } else {
      english = englishVersion(trimmed);
      if (english === null) return;
      // Keep original whitespace only for exact known labels.
      english = current.replace(trimmed, english);
      origin.set(node, english);
    }
    const raw = english.trim();
    const output = lang === 'fr' ? english.replace(raw, translated(raw)) : english;
    if (node.nodeValue !== output) node.nodeValue = output;
  }
  const attrNames = ['placeholder', 'aria-label', 'title', 'alt'];
  const originalAttributes = new WeakMap();

  function applyAttrs(el) {
    if (el.matches(skipParents)) return;
    let saved = originalAttributes.get(el);
    if (!saved) {
      saved = {};
      originalAttributes.set(el, saved);
    }
    for (const attr of attrNames) {
      if (!el.hasAttribute(attr)) continue;
      const current = el.getAttribute(attr);
      if (!current) continue;
      if (saved[attr] === undefined || (current !== saved[attr] && current !== translated(saved[attr]))) {
        const en = englishVersion(current);
        if (en === null) continue;
        saved[attr] = en;
      }
      const output = lang === 'fr' ? translated(saved[attr]) : saved[attr];
      if (current !== output) el.setAttribute(attr, output);
    }
    if (el instanceof HTMLOptionElement && el.dataset.i18nIgnore !== undefined) return;
  }

  function translateTree(root) {
    if (root.nodeType === Node.TEXT_NODE) {
      applyText(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
    if (root.nodeType === Node.ELEMENT_NODE && root.matches(skipParents)) return;
    if (root.nodeType === Node.ELEMENT_NODE) applyAttrs(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (node.nodeType === Node.TEXT_NODE) applyText(node);
      else if (!node.closest(skipParents)) applyAttrs(node);
    }
  }

  function changeLanguage(value) {
    lang = value === 'fr' ? 'fr' : 'en';
    localStorage.setItem(STORAGE_KEY, lang);
    document.documentElement.lang = lang === 'fr' ? 'fr-CA' : 'en-CA';
    document.querySelectorAll('[data-language-choice]').forEach(btn => {
      const active = btn.dataset.languageChoice === lang;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', String(active));
    });
    translateTree(document.body);
    document.dispatchEvent(new CustomEvent('smartstore:languagechange', {
      detail: {
        lang
      }
    }));
  }

  function init() {
    document.querySelectorAll('[data-language-choice]').forEach(btn => btn.addEventListener('click', () => changeLanguage(btn.dataset.languageChoice)));
    const observer = new MutationObserver(changes => {
      const targets = new Set();
      for (const change of changes) {
        if (change.type === 'characterData') targets.add(change.target);
        else if (change.type === 'childList') change.addedNodes.forEach(n => targets.add(n));
      }
      for (const target of targets) translateTree(target);
    });
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true
    });
    changeLanguage(lang);
    // An opt-in helper for page scripts that generate translated notices.
    window.SmartStoreI18n = {
      getLanguage: () => lang,
      setLanguage: changeLanguage,
      t: key => lang === 'fr' ? translated(key) : key,
      formatMoney: value => new Intl.NumberFormat(lang === 'fr' ? 'fr-CA' : 'en-CA', {
        style: 'currency',
        currency: 'CAD'
      }).format(value)
    };
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {
    once: true
  });
  else init();
})();
