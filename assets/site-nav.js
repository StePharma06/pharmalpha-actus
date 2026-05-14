/**
 * Site Navbar Injector - pages Pharm'Actus (variante de pharmalpha.fr/assets/site-nav.js)
 * Rendu strictement identique à la nav principale du site.
 * Inclure via : <script defer src="/assets/site-nav.js?v=20260513a"></script>
 *
 * Spécificités actus (vs nav principale) :
 *   - ROOT absolu (compat actus.pharmalpha.fr en dual push)
 *   - Default __paNavActive = 'actus' si non défini
 *   - Règle CSS défensive pour neutraliser headers natifs des pages d'articles
 *
 * Override lien actif : <script>window.__paNavActive='formations'</script> avant ce script.
 * Valeurs : 'missions' | 'formations' | 'actus' | 'jirai' | 'stephen' | 'inscription'
 */
(function () {
  if (window.__paSiteNavInjected) return;
  window.__paSiteNavInjected = true;

  if (!window.__paNavActive) window.__paNavActive = 'actus';
  var ROOT = 'https://pharmalpha.fr';

  var css = '' +
    '.pa-site-nav{position:fixed;top:0;left:0;right:0;z-index:900;padding:10px 0;background:#0a0a0a;transition:background .35s,padding .35s,box-shadow .35s;}' +
    '.pa-site-nav.solid{background:#fff;padding:6px 0;box-shadow:0 1px 24px rgba(0,0,0,.07);}' +
    '.pa-site-nav-inner{display:flex;align-items:center;justify-content:space-between;flex-wrap:nowrap;max-width:1480px;margin:0 auto;padding:0 28px;gap:18px;}' +
    '.pa-site-nav-logo{flex-shrink:0;display:flex;align-items:center;}' +
    '.pa-site-nav-logo img{height:clamp(51px,5.1vw,93px) !important;width:auto !important;filter:invert(1);transition:filter .35s,height .3s;}' +
    '.pa-site-nav.solid .pa-site-nav-logo img{height:clamp(40px,3vw,52px) !important;filter:none;}' +
    '.pa-site-nav-links{display:flex;align-items:center;gap:2px;list-style:none;padding:0;margin:0;flex-wrap:nowrap;}' +
    '.pa-site-nav-links a{padding:8px 9px;font-size:14px;font-weight:500;color:rgba(255,255,255,.8);border-radius:6px;text-decoration:none;transition:all .3s ease;white-space:nowrap;}' +
    '.pa-site-nav-links a:hover{color:#fff;background:rgba(255,255,255,.07);}' +
    '.pa-site-nav.solid .pa-site-nav-links a{color:#0a0a0a;}' +
    '.pa-site-nav.solid .pa-site-nav-links a:hover{color:#ff914d;background:transparent;}' +
    '.pa-site-nav-links a.active{color:#ff914d;font-weight:700;}' +
    '.pa-site-nav.solid .pa-site-nav-links a.active{color:#ff914d;}' +
    '.pa-site-nav-right{flex-shrink:0;display:flex;align-items:center;gap:12px;}' +
    '.pa-site-nav-btn{display:inline-flex;align-items:center;gap:8px;padding:13px 26px;border-radius:8px;font-size:14px;font-weight:600;letter-spacing:0.01em;text-decoration:none;transition:all .3s ease;white-space:nowrap;cursor:pointer;}' +
    '.pa-site-nav-btn-orange{background:#ff914d;color:#fff;}' +
    '.pa-site-nav-btn-orange:hover{background:#f08236;transform:translateY(-1px);}' +
    '.pa-site-nav-btn-ghost{background:transparent;color:#fff;border:1.5px solid rgba(255,255,255,.3);}' +
    '.pa-site-nav-btn-ghost:hover{border-color:#fff;background:rgba(255,255,255,.06);}' +
    '.pa-site-nav.solid .pa-site-nav-btn-ghost{color:#0a0a0a;border-color:#0a0a0a;}' +
    '.pa-site-nav.solid .pa-site-nav-btn-ghost:hover{background:#0a0a0a;color:#fff;}' +
    '.pa-site-nav-hamburger{display:none;flex-direction:column;gap:5px;padding:4px;cursor:pointer;background:none;border:none;}' +
    '.pa-site-nav-hamburger span{display:block;width:22px;height:2px;background:#fff;border-radius:2px;}' +
    '.pa-site-nav.solid .pa-site-nav-hamburger span{background:#0a0a0a;}' +
    'body.pa-has-nav{padding-top:clamp(80px,calc(6vw + 20px),130px);}' +
    'body.pa-has-nav .header,body.pa-has-nav header.header,body.pa-has-nav .site-header,body.pa-has-nav header.site-header{position:relative !important;top:auto !important;}' +
    '@media (max-width:968px){' +
      'body.pa-has-nav{padding-top:100px;}' +
      '.pa-site-nav{padding:10px 0;}' +
      '.pa-site-nav-inner{position:relative;min-height:80px;justify-content:space-between;}' +
      '.pa-site-nav-logo{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);}' +
      '.pa-site-nav-logo img{height:80px !important;width:auto !important;}' +
      '.pa-site-nav.solid .pa-site-nav-logo img{height:80px !important;}' +
      '.pa-site-nav-links{display:none;}' +
      '.pa-site-nav-right{display:contents;}' +
      '.pa-site-nav-right .pa-site-nav-btn-ghost{display:none;}' +
      '.pa-site-nav-right .pa-site-nav-btn-orange{order:-1;padding:11px 13px;gap:0;}' +
      '.pa-site-nav-right .pa-site-nav-btn-text{display:none;}' +
      '.pa-site-nav-hamburger{order:1;display:flex;}' +
    '}' +
    '.pa-mobile-menu{display:none;position:fixed;inset:0;z-index:950;background:#0a0a0a;flex-direction:column;align-items:center;justify-content:center;gap:28px;}' +
    '.pa-mobile-menu.open{display:flex;}' +
    '.pa-mobile-menu a{font-size:22px;font-weight:600;color:#fff;text-decoration:none;transition:color .2s;}' +
    '.pa-mobile-menu a:hover{color:#ff914d;}' +
    '.pa-mm-close{position:absolute;top:20px;right:24px;font-size:36px;color:#fff;cursor:pointer;background:none;border:none;line-height:1;}';

  var style = document.createElement('style');
  style.id = 'pa-site-nav-style';
  style.textContent = css;
  document.head.appendChild(style);

  function a(key, label, href) {
    var active = (window.__paNavActive === key) ? ' class="active"' : '';
    return '<li><a href="' + href + '"' + active + '>' + label + '</a></li>';
  }

  var html = '' +
    '<div class="pa-mobile-menu" id="paMobileMenu">' +
      '<button class="pa-mm-close" aria-label="Fermer" onclick="paCloseMM()">&times;</button>' +
      '<a href="' + ROOT + '/#services" onclick="paCloseMM()">Mes missions</a>' +
      '<a href="' + ROOT + '/#formations" onclick="paCloseMM()">Formations</a>' +
      '<a href="' + ROOT + '/actus" onclick="paCloseMM()">Pharm\'Actus</a>' +
      '<a href="' + ROOT + '/#jirai" onclick="paCloseMM()">J\'irai dans votre pharmacie</a>' +
      '<a href="' + ROOT + '/stephen-robert" onclick="paCloseMM()">Stephen Robert</a>' +
    '</div>' +
    '<nav class="pa-site-nav" id="paSiteNav">' +
      '<div class="pa-site-nav-inner">' +
        '<a href="' + ROOT + '/" class="pa-site-nav-logo" aria-label="Retour Pharm\'Alpha">' +
          '<img src="' + ROOT + '/Logos/Logo sans fond/2-tight.png" alt="Pharm\'Alpha Consulting">' +
        '</a>' +
        '<ul class="pa-site-nav-links">' +
          a('missions', 'Mes missions', ROOT + '/#services') +
          a('formations', 'Formations', ROOT + '/#formations') +
          a('actus', 'Pharm\'Actus', ROOT + '/actus') +
          a('jirai', 'J\'irai dans votre pharmacie', ROOT + '/#jirai') +
          a('stephen', 'Stephen Robert', ROOT + '/stephen-robert') +
        '</ul>' +
        '<div class="pa-site-nav-right">' +
          '<a href="' + ROOT + '/inscription" class="pa-site-nav-btn pa-site-nav-btn-ghost' + (window.__paNavActive === 'inscription' ? ' active' : '') + '">M\'inscrire à une formation</a>' +
          '<a href="' + ROOT + '/#contactForm" class="pa-site-nav-btn pa-site-nav-btn-orange" aria-label="Me contacter">' +
            '<svg class="pa-site-nav-btn-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 5L2 7"/></svg>' +
            '<span class="pa-site-nav-btn-text">Me contacter</span>' +
          '</a>' +
          '<button class="pa-site-nav-hamburger" aria-label="Menu" onclick="paOpenMM()">' +
            '<span></span><span></span><span></span>' +
          '</button>' +
        '</div>' +
      '</div>' +
    '</nav>';

  function inject() {
    document.body.classList.add('pa-has-nav');
    var wrap = document.createElement('div');
    wrap.innerHTML = html;
    while (wrap.firstChild) document.body.insertBefore(wrap.firstChild, document.body.firstChild);

    var nav = document.getElementById('paSiteNav');
    function onScroll() {
      nav.classList.toggle('solid', window.scrollY > 50);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }

  window.paOpenMM = function () { document.getElementById('paMobileMenu').classList.add('open'); document.body.style.overflow = 'hidden'; };
  window.paCloseMM = function () { document.getElementById('paMobileMenu').classList.remove('open'); document.body.style.overflow = ''; };
})();
