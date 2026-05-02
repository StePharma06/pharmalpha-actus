/**
 * Klaro CMP — Configuration Pharm'Alpha
 * Conforme RGPD + délibération CNIL 2020-091 + Google Consent Mode v2
 * Doc : https://klaro.org/
 */
(function () {
  // Initialiser Consent Mode v2 en mode "denied" par défaut (avant toute interaction)
  window.dataLayer = window.dataLayer || [];
  function gtag() { dataLayer.push(arguments); }
  window.gtag = gtag;
  gtag('consent', 'default', {
    'ad_storage': 'denied',
    'ad_user_data': 'denied',
    'ad_personalization': 'denied',
    'analytics_storage': 'denied',
    'functionality_storage': 'granted',
    'security_storage': 'granted',
    'wait_for_update': 500
  });

  // Configuration Klaro
  window.klaroConfig = {
    version: 1,
    elementID: 'klaro',
    storageMethod: 'cookie',
    cookieName: 'pharmalpha-consent',
    cookieExpiresAfterDays: 365,
    privacyPolicy: '/confidentialite',
    default: false,
    mustConsent: false,
    acceptAll: true,
    hideDeclineAll: false,
    hideLearnMore: false,
    noticeAsModal: false,
    htmlTexts: true,
    embedded: false,
    groupByPurpose: true,
    lang: 'fr',
    translations: {
      fr: {
        consentModal: {
          title: 'Cookies & confidentialité',
          description: "Nous utilisons des cookies pour mesurer l'audience du site et améliorer ton expérience. Tu peux accepter, refuser ou personnaliser tes choix. <a href='/cookies'>En savoir plus</a>."
        },
        consentNotice: {
          changeDescription: "Tes préférences ont changé.",
          description: "Salut ! Pour mesurer l'audience du site et l'améliorer, on aimerait poser quelques cookies. Tu choisis : <a href='#' class='cm-link cm-learn-more'>en savoir plus</a>",
          learnMore: 'Personnaliser',
          testing: 'Mode test'
        },
        ok: 'Tout accepter',
        save: 'Enregistrer',
        decline: 'Refuser',
        close: 'Fermer',
        acceptAll: 'Tout accepter',
        acceptSelected: 'Enregistrer mes choix',
        service: {
          disableAll: {
            title: 'Activer ou désactiver tous les services',
            description: 'Utilise ce bouton pour activer ou désactiver tous les services en une fois.'
          },
          optOut: {
            title: '(opt-out)',
            description: "Ce service est chargé par défaut (mais tu peux te désinscrire)"
          },
          required: {
            title: '(obligatoire)',
            description: "Ce service est nécessaire au fonctionnement du site"
          },
          purposes: 'Finalités',
          purpose: 'Finalité'
        },
        purposes: {
          analytics: {
            title: 'Mesure d\'audience',
            description: "Pour comprendre comment tu utilises le site et l'améliorer."
          },
          functional: {
            title: 'Fonctionnel',
            description: "Pour mémoriser tes préférences (langue, choix cookies)."
          }
        },
        poweredBy: 'Géré par Klaro!',
        privacyPolicyUrl: '/confidentialite',
        contextualConsent: {
          description: 'Veux-tu charger le contenu externe fourni par {title} ?',
          acceptOnce: 'Oui',
          acceptAlways: 'Toujours'
        }
      }
    },

    services: [
      {
        name: 'google-analytics',
        title: 'Google Analytics 4',
        description: "Mesure d'audience anonymisée — IP masquée, conservation 14 mois.",
        purposes: ['analytics'],
        cookies: [
          [/^_ga.*$/, '/', '.pharmalpha.fr']
        ],
        callback: function (consent, service) {
          // Met à jour Google Consent Mode v2 quand l'utilisateur change ses choix
          if (consent) {
            gtag('consent', 'update', {
              'analytics_storage': 'granted'
            });
          } else {
            gtag('consent', 'update', {
              'analytics_storage': 'denied'
            });
          }
        },
        required: false,
        optOut: false,
        onlyOnce: true
      },
      {
        name: 'youtube',
        title: 'YouTube',
        description: "Lecture vidéos intégrées (mode no-cookie quand possible).",
        purposes: ['functional'],
        cookies: [],
        required: false,
        optOut: false,
        onlyOnce: true,
        contextualConsentOnly: true
      }
    ]
  };
})();
