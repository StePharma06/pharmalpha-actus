/* Transparence IA (reglement UE 2024/1689, art. 50) : ligne de source et paragraphe d'information d'un article,
   affiches dans les fenetres de lecture de /actus et des archives.

   MIROIR de update_actus._ai_disclosure (avis d'Emilie du 2026-10-02, section 8.2 et 8.5). Les textes sont ceux
   de l'avis, mot pour mot. Ne jamais en changer un ici sans changer update_actus.py : scripts/test_ia_disclosure.py
   compare les deux implementations sur tous les articles de articles.json et echoue a la moindre difference.

   Ordre de selection, identique au pipeline :
     1. LSV (categorie "lsv" ou identifiant "lsv_")
     2. Business (categorie "business_officine"), avec ou sans media
     3. media nomme, Pharm'Alpha et Pharm'Actus exclus
     4. tout le reste : variante generique (ne dit rien de la provenance, donc toujours exacte)

   Aucune insertion de HTML : tout passe par textContent et createElement. */
(function (root) {
  'use strict';

  var TAIL = "Il peut contenir des erreurs : pour toute information réglementaire ou chiffrée, reportez-vous à la source officielle. " +
    "Il ne constitue ni un avis médical ou pharmaceutique, ni un conseil juridique ou fiscal.";
  var GENERIC = "Ce texte a été généré par une intelligence artificielle, puis publié automatiquement, sans relecture humaine préalable. " + TAIL;
  var LSV = "Ce texte a été généré par une intelligence artificielle, sans source de presse, puis publié automatiquement, " +
    "sans relecture humaine préalable. Les faits historiques sont à vérifier avant d'être cités. " + TAIL;
  var BUSINESS = "Ce texte est une synthèse générée par une intelligence artificielle à partir de titres et de résumés d'articles de presse, " +
    "puis publiée automatiquement, sans relecture humaine préalable. Il peut contenir des informations qui ne figurent dans aucune de ces sources, " +
    "y compris des chiffres et des références, et les sources citées en fin de texte ont été indiquées par l'intelligence artificielle sans avoir été vérifiées. " +
    "Pour toute information réglementaire, chiffrée ou financière, reportez-vous à la source officielle. " +
    "Il ne constitue ni un avis médical ou pharmaceutique, ni un conseil juridique, fiscal ou de gestion.";

  var DASHES = String.fromCharCode(0x2013, 0x2014);
  var COMPOSITE_PREFIX = new RegExp("^Pharm'Actus\\s*[·:" + DASHES + "-]*\\s*");
  var FIRST_DASH = new RegExp("\\s*[" + DASHES + "]\\s*|\\s+-\\s+");
  var OFFICIAL_TEXT = /^(?:décret|arrêté|loi|ordonnance|circulaire)(?![\p{L}\p{N}_])/iu;
  var NOT_A_MEDIA = new RegExp("^pharm['" + String.fromCharCode(0x2019) + "]?\\s*(?:alpha|actus)(?![\\p{L}\\p{N}_])", "iu");

  /* Miroir de update_actus._ai_source_label : le media a nommer, "" s'il n'y en a pas. */
  function sourceLabel(sourceName) {
    var s = String(sourceName == null ? '' : sourceName).trim();
    var composite = s.indexOf("Pharm'Actus") === 0;
    if (composite) {
      s = s.replace(COMPOSITE_PREFIX, '');
    }
    var m = s.match(FIRST_DASH);
    if (m) {
      var before = s.slice(0, m.index);
      var after = s.slice(m.index + m[0].length);
      s = OFFICIAL_TEXT.test(before) ? after : before;
    }
    if (composite) {
      s = s.split(', ')[0];
    }
    s = s.replace(/\s+/g, ' ').replace(/^[ .;:]+|[ .;:]+$/g, '');
    if (s.length > 90) {
      var cut = s.slice(0, 90);
      var space = cut.lastIndexOf(' ');
      s = space >= 0 ? cut.slice(0, space) : cut;
    }
    return NOT_A_MEDIA.test(s) ? '' : s;
  }

  /* Miroir de update_actus._ai_disclosure. a = { id, categorie, source, source_url }.
     Retourne { variant, lead, media, url, tail, paragraph } : lead est la ligne de source ("" s'il n'y en a pas). */
  function disclosure(a) {
    a = a || {};
    var id = String(a.id == null ? '' : a.id);
    var categorie = String(a.categorie == null ? '' : a.categorie);
    var media = sourceLabel(a.source);
    var url = String(a.source_url == null ? '' : a.source_url).trim();
    if (!/^https?:\/\//.test(url)) {
      url = '';
    }
    if (categorie === 'lsv' || id.indexOf('lsv_') === 0) {
      return { variant: 'lsv', lead: '', media: '', url: '', tail: '', paragraph: LSV };
    }
    if (categorie === 'business_officine') {
      var line = !!(media && url);
      return {
        variant: 'business',
        lead: line ? "Première source indiquée par l'intelligence artificielle :" : '',
        media: line ? media : '', url: line ? url : '', tail: line ? '.' : '', paragraph: BUSINESS
      };
    }
    if (media) {
      return {
        variant: 'standard', lead: 'Point de départ :', media: media, url: url, tail: ' (titre et résumé).',
        paragraph: "Ce texte a été généré par une intelligence artificielle à partir du titre et du résumé publiés par " + media +
          ", puis publié automatiquement, sans relecture humaine préalable. " + TAIL
      };
    }
    return { variant: 'generic', lead: '', media: '', url: '', tail: '', paragraph: GENERIC };
  }

  /* Remplit la ligne de source (sourceEl) et le paragraphe d'information (infoEl). Une erreur de calcul retombe sur la
     variante generique : jamais le texte d'un article precedent. onSourceClick : suivi de clic facultatif. */
  function render(a, sourceEl, infoEl, onSourceClick) {
    var d;
    try {
      d = disclosure(a);
    } catch (e) {
      d = { variant: 'generic', lead: '', media: '', url: '', tail: '', paragraph: GENERIC };
    }
    infoEl.textContent = d.paragraph;
    sourceEl.textContent = '';
    if (!d.lead) {
      return d;
    }
    var strong = document.createElement('strong');
    strong.textContent = d.lead;
    sourceEl.appendChild(strong);
    sourceEl.appendChild(document.createTextNode(' '));
    if (d.url) {
      var link = document.createElement('a');
      link.href = d.url;
      link.target = '_blank';
      link.rel = 'nofollow noopener';
      link.textContent = d.media;
      if (typeof onSourceClick === 'function') {
        link.addEventListener('click', onSourceClick);
      }
      sourceEl.appendChild(link);
    } else {
      sourceEl.appendChild(document.createTextNode(d.media));
    }
    sourceEl.appendChild(document.createTextNode(d.tail));
    return d;
  }

  root.iaDisclosure = { sourceLabel: sourceLabel, disclosure: disclosure, render: render };
})(typeof window !== 'undefined' ? window : globalThis);
