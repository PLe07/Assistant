// Tableau de bord : mise à jour en direct (SSE), actions (POST avec le jeton), thème clair/sombre.
// Aucun script en ligne, aucune ressource extérieure : tout passe par cette page locale.
(() => {
  'use strict';
  const jeton = new URLSearchParams(window.location.search).get('t') || '';
  const contenu = document.getElementById('contenu');
  const direct = document.getElementById('etat-direct');
  const resultat = document.getElementById('resultat');
  const racine = document.documentElement;

  // --- thème -------------------------------------------------------------------------------------------------------
  const boutonTheme = document.getElementById('theme');
  const sombreSysteme = () => window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const themeActuel = () => racine.dataset.theme || (sombreSysteme() ? 'dark' : 'light');
  try {
    const garde = window.localStorage.getItem('theme');
    if (garde === 'dark' || garde === 'light') racine.dataset.theme = garde;
  } catch (e) { /* stockage indisponible : le réglage du Mac suffit */ }
  if (boutonTheme) {
    boutonTheme.setAttribute('aria-pressed', String(themeActuel() === 'dark'));
    boutonTheme.addEventListener('click', () => {
      racine.dataset.theme = themeActuel() === 'dark' ? 'light' : 'dark';
      boutonTheme.setAttribute('aria-pressed', String(racine.dataset.theme === 'dark'));
      try { window.localStorage.setItem('theme', racine.dataset.theme); } catch (e) { /* rien */ }
    });
  }

  // --- en direct ---------------------------------------------------------------------------------------------------
  let enCours = false;
  async function recharger() {
    const adresse = contenu && contenu.dataset.fragment;
    if (!adresse || enCours) return;
    enCours = true;
    try {
      const actif = document.activeElement && contenu.contains(document.activeElement) ? document.activeElement : null;
      const cle = actif ? (actif.getAttribute('href') || actif.dataset.action || '') : '';
      const ouverts = Array.from(contenu.querySelectorAll('details[open] summary')).map((s) => s.textContent);
      const r = await fetch(adresse, { cache: 'no-store', credentials: 'same-origin' });
      if (!r.ok) return;
      contenu.innerHTML = await r.text();
      // On rend le focus et les tableaux ouverts là où ils étaient (navigation au clavier).
      contenu.querySelectorAll('details summary').forEach((s, i) => {
        if (ouverts.includes(s.textContent) && s.parentElement) s.parentElement.open = true;
      });
      if (cle) {
        const retrouve = Array.from(contenu.querySelectorAll('a, button'))
          .find((el) => (el.getAttribute('href') || el.dataset.action || '') === cle);
        if (retrouve) retrouve.focus();
      }
    } finally {
      enCours = false;
    }
  }
  if (window.EventSource && contenu && contenu.dataset.fragment) {
    const flux = new EventSource('/evenements?t=' + encodeURIComponent(jeton));
    flux.addEventListener('maj', () => { recharger().catch(() => {}); });
    flux.addEventListener('open', () => { if (direct) direct.textContent = 'En direct'; });
    flux.addEventListener('error', () => { if (direct) direct.textContent = 'Reconnexion…'; });
    window.addEventListener('pagehide', () => flux.close());
  }

  // --- actions -----------------------------------------------------------------------------------------------------
  function afficher(donnees) {
    if (!resultat) return;
    resultat.textContent = '';
    const texte = document.createElement('p');
    texte.textContent = donnees.message || (donnees.ok === false ? 'La commande a échoué.' : 'Fait.');
    resultat.appendChild(texte);
    if (donnees.commande) {
      const code = document.createElement('pre');
      code.textContent = donnees.commande;
      resultat.appendChild(code);
    }
    if (Array.isArray(donnees.ecarts) && donnees.ecarts.length) {
      const liste = document.createElement('ul');
      donnees.ecarts.slice(0, 50).forEach((e) => {
        const li = document.createElement('li');
        li.textContent = (e.chemin || '?') + ' : ' + (e.genre || '?');
        liste.appendChild(li);
      });
      resultat.appendChild(liste);
    }
    if (typeof donnees.sortie === 'string' && donnees.sortie) {
      const sortie = document.createElement('pre');
      sortie.textContent = donnees.sortie;
      resultat.appendChild(sortie);
    }
    resultat.scrollIntoView({ block: 'nearest' });
  }

  document.addEventListener('click', async (evenement) => {
    const bouton = evenement.target.closest && evenement.target.closest('button[data-action]');
    if (!bouton) return;
    if (bouton.dataset.confirmer && !window.confirm(bouton.dataset.confirmer)) return;
    bouton.disabled = true;
    try {
      const r = await fetch(bouton.dataset.action + '?t=' + encodeURIComponent(jeton), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Jeton': jeton },
        body: bouton.dataset.corps || '{}',
        credentials: 'same-origin',
      });
      const donnees = await r.json().catch(() => ({ message: 'Réponse illisible (' + r.status + ').' }));
      afficher(donnees);
    } catch (e) {
      afficher({ message: 'La page locale ne répond pas : le tableau de bord tourne-t-il ?' });
    } finally {
      bouton.disabled = false;
    }
  });
})();
