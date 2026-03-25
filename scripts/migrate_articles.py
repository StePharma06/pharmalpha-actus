#!/usr/bin/env python3
"""
Migration script: rewrite formal articles in Stephen's tone,
replace DALL-E images with Pexels photos, remove duplicates.
"""
import os, re, json, time, requests

PEXELS_KEY = "UapwydwlfWpQrgkN8rfyClS3foJ6zuFYyL4UVqFYtomh7tlTVcM5t6g1"
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
INDEX_HTML = os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html")

# ============================================================
# CLEAN ARTICLE LIST (duplicates removed, formal articles rewritten)
# ============================================================
ARTICLES = [
  {
    "id": "actu_2026_03_25_1_b",
    "date": "2026-03-25",
    "type": "actu",
    "categorie": "pharma_france",
    "titre": "Vaccins grippe : tes marges sauvées pour 2025 !",
    "resume": "Le ministère fait marche arrière sur l'égalisation des marges entre vaccins standards et améliorés. Une victoire syndicale qui préserve ta rentabilité sur la campagne 2025. Mais attention, ce n'est que partie remise...",
    "full_text": "Le ministère de la Santé vient de confirmer l'abandon de l'égalisation des marges sur les vaccins antigrippaux pour 2025. Une excellente nouvelle pour ton chiffre d'affaires.\n\nConcrètement, tu gardes tes marges actuelles sur les vaccins \"améliorés\" comme Efluelda ou Fluzone HD. Pas de nivellement par le bas cette année. Les syndicats ont fait le boulot.\n\nMais ne crie pas victoire trop vite. Le projet n'est pas enterré, juste reporté. Le ministère garde cette épée de Damoclès pour les prochaines campagnes. Et devine quoi ? Aucune info sur les autres effecteurs et leurs stocks.\n\nPour cette campagne 2025, tu peux commander sereinement. Tes calculs de rentabilité restent valables. Mais prépare-toi mentalement : ce répit ne durera pas éternellement.",
    "source": "Le Moniteur des Pharmacies",
    "source_url": "https://www.lemoniteurdespharmacies.fr/profession/socio-professionnel/egalisation-des-marges-sur-les-vaccins-antigrippaux-une-premiere-bataille-gagnee-mais",
    "tiktok_url": "",
    "badge_label": "Pharma France",
    "pexels_query": "flu vaccine pharmacy"
  },
  {
    "id": "actu_2026_03_25_2_b",
    "date": "2026-03-25",
    "type": "actu",
    "categorie": "pharma_france",
    "titre": "Aide à mourir : ton rôle va exploser (et c'est flou)",
    "resume": "Le projet de loi sur l'aide à mourir te confie une mission centrale : analyse, préparation, dispensation et gestion des retours. L'Académie de pharmacie réclame des clarifications urgentes sur ce nouveau périmètre d'activité.",
    "full_text": "L'aide à mourir débarque dans ton officine avec un rôle majeur pour toi. Le texte te confie toute la chaîne pharmaceutique : de l'analyse de prescription à la gestion des retours.\n\nMais l'Académie de pharmacie tire la sonnette d'alarme. Cette mission ne peut pas être assimilée à un acte de dispensation classique. Il faut des règles spécifiques, une formation dédiée, des protocoles précis.\n\nQu'est-ce que ça change concrètement ? Tu vas devoir gérer des situations ultra-sensibles avec des familles en détresse. Préparer des produits spécifiques. Récupérer les éventuels non-utilisés. Tout ça sans cadre juridique clair pour l'instant.\n\nLa profession pousse pour des clarifications rapides. Parce que sur un sujet aussi lourd, l'improvisation n'est pas une option. Tes responsabilités vont exploser, autant que ce soit cadré.",
    "source": "Le Moniteur des Pharmacies",
    "source_url": "https://www.lemoniteurdespharmacies.fr/profession/socio-professionnel/aide-a-mourir-de-la-necessite-de-clarifier-la-place-du-pharmacien",
    "tiktok_url": "",
    "badge_label": "Pharma France",
    "pexels_query": "end of life care hospital"
  },
  {
    "id": "actu_2026_03_25_3_b",
    "date": "2026-03-25",
    "type": "actu",
    "categorie": "pharma_france",
    "titre": "Pénuries de psychotropes : le Conseil d'État saisi !",
    "resume": "Un syndicat de médecins attaque l'État devant le Conseil d'État sur les pénuries de psychotropes. Objectif : faire reconnaître la responsabilité du ministère et de l'ANSM dans ces ruptures qui pourrissent ton quotidien.",
    "full_text": "Les médecins passent à l'offensive sur les pénuries de psychotropes. Direction Conseil d'État pour attaquer frontalement le ministère de la Santé et l'ANSM.\n\nLeur stratégie ? Faire reconnaître la responsabilité de l'État dans ces ruptures chroniques qui te pourrissent la vie au comptoir. Après une mise en demeure restée lettre morte, ils sortent l'artillerie lourde.\n\nTu le sais mieux que personne : antidépresseurs, anxiolytiques, antipsychotiques... Les rayons se vident régulièrement. Tes patients dépriment, tu cherches des alternatives, tu perds du temps et de l'argent.\n\nSi le Conseil d'État donne raison aux médecins, ça pourrait changer la donne. L'État devrait enfin prendre ses responsabilités sur l'approvisionnement. Et toi, tu pourrais retrouver des rayons pleins et des patients moins stressés.",
    "source": "Le Quotidien du Pharmacien",
    "source_url": "http://www.lequotidiendupharmacien.fr/le-conseil-detat-saisi-sur-la-question-des-penuries-de-psychotropes",
    "tiktok_url": "",
    "badge_label": "Pharma France",
    "pexels_query": "empty pharmacy shelves medicine"
  },
  {
    "id": "lsv_2026_03_25",
    "date": "2026-03-25",
    "type": "lsv",
    "categorie": "lsv",
    "titre": "Le saviez-vous ? Quand la morphine était vendue en pharmacie sans ordonnance",
    "resume": "Tu croyais que les opioïdes c'était hyper réglementé depuis toujours ? Figure-toi que jusqu'aux années 1920, tu pouvais acheter de la morphine comme du paracétamol aujourd'hui. Spoiler alert : ça a créé un vrai problème de santé publique.",
    "full_text": "Imagine un peu. Début du XXe siècle, tu entres dans une pharmacie parisienne ou new-yorkaise. Le pharmacien te propose de la morphine en flacon, de l'opium en poudre, de la codéine en sirop pour la toux. Zéro ordonnance, zéro question. C'était juste... un produit de base du comptoir, comme l'aspirine.\n\nLa morphine, découverte en 1805 par le pharmacien allemand Friedrich Sertürner, était devenue LA molécule miracle. Douleurs ? Morphine. Insomnie ? Morphine. Diarrhée ? Morphine aussi, tiens. Les labos l'ajoutaient partout : toniques, sirops, pommades. C'était le remède universel. Et puis il y a eu les guerres. Les soldats blessés recevaient de la morphine en masse. Certains sont revenus... dépendants. Très dépendants.\n\nLe truc fou ? Personne ne parlait de dépendance à l'époque. On appelait ça une \" habitude \". Les médecins prescrivaient, les pharmaciens vendaient, les gens consommaient. Jusqu'à ce qu'on réalise qu'on avait créé une génération entière de dépendants.\n\nC'est pour ça qu'en 1920-1930, les gouvernements ont dit : stop. Fini la vente libre. La morphine devient un médicament strictement réglementé. Les États-Unis passent le Harrison Narcotic Tax Act en 1914. La France emboîte le pas. Et nous, pharmaciens, on devient les gardiens d'une frontière très claire entre \" produit de vente libre \" et \" médicament dangereux \".\n\nAujourd'hui au comptoir, quand un patient te demande un tramadol ou de la codéine, tu sais exactement pourquoi tu dois demander une ordonnance. C'est pas juste de la bureaucratie. C'est le fruit d'une leçon coûteuse du siècle dernier.",
    "source": "Pharm'Alpha",
    "source_url": "",
    "tiktok_url": "",
    "badge_label": "Le Saviez-Vous",
    "pexels_query": "vintage pharmacy bottles old"
  },
  {
    "id": "actu_2026_03_24_1",
    "date": "2026-03-24",
    "type": "actu",
    "categorie": "pharma_france",
    "titre": "Pharmaciens en galère : l'ADOP tire la sonnette d'alarme",
    "resume": "L'ADOP croule sous les appels de pharmaciens en difficulté financière. Le moral de la profession est au plus bas. Si tu te sens isolé, tu n'es pas seul — et il existe des solutions.",
    "full_text": "Ça fait mal à lire, mais il faut en parler. L'ADOP — la ligne d'écoute dédiée aux pharmaciens — voit les appels exploser. Et le motif principal ? L'argent.\n\nPression sur les marges, charges qui grimpent, approvisionnement en dents de scie... Le cocktail est toxique. Et quand les finances flanchent, le moral suit. C'est mécanique.\n\nSi tu te reconnais là-dedans, sache que tu n'es pas seul. L'ADOP propose un accompagnement gratuit et confidentiel, 7j/7. Que tu sois titulaire, adjoint ou préparateur, tu peux appeler et trouver une oreille qui comprend ta réalité.\n\nCe constat, révélé à PharmagoraPlus, c'est un signal fort. La profession souffre. Et la première étape pour s'en sortir, c'est d'en parler.",
    "source": "Le Quotidien du Pharmacien",
    "source_url": "http://www.lequotidiendupharmacien.fr/exercice-pro/les-problemes-economiques-pesent-de-plus-en-plus-sur-le-moral-des-pharmaciens",
    "tiktok_url": "",
    "badge_label": "Pharma France",
    "pexels_query": "pharmacy store front"
  },
  {
    "id": "actu_2026_03_24_2",
    "date": "2026-03-24",
    "type": "actu",
    "categorie": "pharma_france",
    "titre": "Vaccins méningo : remboursement élargi, c'est maintenant !",
    "resume": "Nimenrix, Menveo et Bexsero sont remboursés pour les enfants nés entre 2020 et 2022. Si t'as des parents qui hésitaient à cause du prix, c'est le moment de les relancer.",
    "full_text": "L'Assurance maladie vient d'élargir le remboursement des vaccins anti-méningocoques. Et ça concerne une tranche d'âge qu'on avait un peu oubliée.\n\nConcrètement : les enfants nés en 2020, 2021 et 2022 peuvent maintenant se faire vacciner avec Nimenrix, Menveo (ACWY) et Bexsero (B) avec prise en charge. Ces gamins n'étaient pas concernés par l'obligation vaccinale de 2023. Un trou dans la raquette, corrigé.\n\nAu comptoir, ça change quoi ? Tu peux facturer directement. Vérifie bien la date de naissance sur l'ordonnance et c'est parti.\n\nEt surtout : pense à relancer les parents concernés. Beaucoup ont zappé la vaccination parce que c'était pas remboursé. Maintenant, il n'y a plus d'excuse.",
    "source": "Le Quotidien du Pharmacien",
    "source_url": "http://www.lequotidiendupharmacien.fr/exercice-pro/vaccins-meningococciques-b-et-acwy-tous-rembourses-pour-les-enfants-nes-entre-2020-et-2024",
    "tiktok_url": "",
    "badge_label": "Pharma France",
    "pexels_query": "child vaccination pediatric"
  },
  {
    "id": "actu_2026_03_24_3",
    "date": "2026-03-24",
    "type": "actu",
    "categorie": "sante",
    "titre": "Méningite : ça chauffe en Angleterre, vigilance au comptoir",
    "resume": "34 cas en Angleterre, 2 décès, un mort en France à La Hague. L'épidémie est surveillée de près. Prépare-toi aux questions des patients et vérifie tes stocks de vaccins.",
    "full_text": "L'Angleterre fait face à une épidémie de méningite sérieuse : 34 cas, 2 décès. L'épicentre ? Canterbury, une discothèque. Les Anglais vaccinent à tour de bras dans le Kent.\n\nEn France, on n'est pas directement touchés, mais un décès à La Hague (salariée d'Orano) a mis tout le monde en alerte. 50 cas contacts sous surveillance. Pas de lien avec l'épisode anglais, mais la proximité géographique impose la prudence.\n\nCe que ça change pour toi : les patients vont poser des questions. Les parents vont flipper. Les demandes de vaccination vont augmenter, surtout chez les 16-24 ans.\n\nLes signaux d'alerte à connaître : fièvre brutale, céphalées intenses, raideur de nuque, purpura. Si un patient te décrit ça, c'est urgence absolue. Orientation immédiate aux urgences, pas de tergiversation.",
    "source": "France Info Sante",
    "source_url": "https://www.franceinfo.fr/sante/maladie/meningite/meningite-grand-danger-pour-les-plus-jeunes_7889306.html",
    "tiktok_url": "",
    "badge_label": "Sante",
    "pexels_query": "hospital emergency health alert"
  },
  {
    "id": "lsv_1",
    "date": "2026-03-24",
    "type": "lsv",
    "categorie": "lsv",
    "titre": "Le saviez-vous ? De l'écorce de saule à l'acide acétylsalicylique",
    "resume": "3 500 ans d'histoire pharmacologique. Du saule blanc des Égyptiens à la synthèse de Hoffmann en 1897 : retour sur la naissance du premier médicament industriel.",
    "full_text": "L'acide acétylsalicylique, qu'on dispense chaque jour au comptoir, a 3 500 ans d'histoire pharmacologique derrière lui.\n\nTout commence avec le saule blanc (Salix alba). Les Égyptiens utilisaient déjà des décoctions d'écorce comme antipyrétique et antalgique. Le principe actif, la salicine, est un glucoside qui sera isolé en 1829 par Pierre-Joseph Leroux, pharmacien français.\n\nEn 1853, Charles Frédéric Gerhardt (chimiste alsacien) réalise la première acétylation de l'acide salicylique. Mais c'est Felix Hoffmann, chimiste chez Bayer, qui stabilise la synthèse en 1897. Motivation : son père souffrait de polyarthrite rhumatoïde et ne tolérait plus le salicylate de sodium (trop gastrotoxique).\n\n1899 : Bayer commercialise l'Aspirine. Premier médicament industriel sous forme de comprimé. Le nom vient du \"a\" d'acétyl et de \"spir\" pour Spiraea (la reine-des-prés, autre source de salicylés).\n\nAujourd'hui, 40 000 tonnes/an dans le monde. Et on découvre encore de nouvelles indications : au-delà de l'analgésie et l'antiagrégation plaquettaire, des études explorent son rôle en prévention du cancer colorectal. Une molécule qu'on n'a pas fini d'étudier.",
    "source": "Pharm'Alpha",
    "source_url": "",
    "tiktok_url": "",
    "badge_label": "Le Saviez-Vous",
    "pexels_query": "aspirin white pills"
  },
  {
    "id": "actu_2026_03_23_1",
    "date": "2026-03-23",
    "type": "actu",
    "categorie": "pharma_france",
    "titre": "Biosimilaires : la LFSS 2026 change la donne en officine",
    "resume": "La LFSS 2026 élargit le droit de substitution des biosimilaires et introduit un intéressement financier pour les officines. Le marché pèse déjà 1,2 Md EUR en ville.",
    "full_text": "La LFSS 2026 marque un tournant pour la substitution des biosimilaires en officine. Le droit de substitution, jusqu'ici limité à quelques DCI, s'élargit significativement. Et surtout, un mécanisme d'intéressement financier est mis en place pour les pharmaciens qui substituent.\n\nConcrètement, la marge sur les biosimilaires est désormais plus favorable que sur les bioréférences. L'écart de prix de 20 à 40% entre biosimilaire et princeps se traduit par un gain net pour l'officine, à condition de maîtriser la substitution et de rassurer le patient.\n\nLe marché pèse déjà 1,2 milliard d'euros en ville. Les principales DCI concernées : adalimumab, étanercept, trastuzumab, insuline glargine. Les volumes restent en dessous du potentiel, avec un taux de substitution autour de 30% seulement.\n\nPoint de vigilance : la substitution reste encadrée. Vérifier l'absence de mention NS sur l'ordonnance et assurer la continuité de traitement — pas de switch entre deux biosimilaires différents en cours de traitement.\n\nC'est un levier de marge concret pour l'officine, à condition de former les équipes et d'accompagner les patients dans la transition.",
    "source": "Le Moniteur des Pharmacies",
    "source_url": "https://www.lemoniteurdespharmacies.fr/business/marches/medicaments-biosimilaires-2026-vers-une-substitution-reussie",
    "tiktok_url": "",
    "badge_label": "Pharma France",
    "pexels_query": "pharmaceutical laboratory medicine"
  },
  {
    "id": "actu_2026_03_23_2",
    "date": "2026-03-23",
    "type": "actu",
    "categorie": "pharma_monde",
    "titre": "Sémaglutide : 40+ génériques indiens à 13 EUR, quel impact pour nous ?",
    "resume": "Les brevets de Novo Nordisk sur la sémaglutide tombent en Inde. Plus de 40 labos lancent leurs génériques. En Europe, protection jusqu'en 2031, mais le signal prix est fort.",
    "full_text": "Les brevets de Novo Nordisk sur la sémaglutide (Ozempic, Wegovy) tombent en Inde. Résultat : plus de 40 laboratoires indiens lancent leurs génériques, certains à 13 EUR/mois. Contre plus de 200 EUR en Europe.\n\nPour l'instant, ça ne change rien à ton comptoir. Les brevets européens sont protégés jusqu'en 2031 minimum. Mais le signal est clair : la sémaglutide va devenir un blockbuster générique mondial dans les prochaines années.\n\nCe qu'il faut surveiller : les demandes d'AMM via la procédure centralisée EMA. Plusieurs labos indiens (Dr. Reddy's, Sun Pharma, Cipla) ont déjà des dossiers en cours. L'arrivée de biosimilaires/génériques injectables de sémaglutide en Europe pourrait redistribuer les cartes.\n\nEn attendant, la pression au comptoir est déjà là. Les patients voient les prix indiens en ligne, les ruptures d'Ozempic persistent, et les détournements d'usage (perte de poids hors AMM) compliquent la dispensation.\n\nÀ suivre de près : quand les génériques arriveront en Europe, le modèle de marge sera totalement différent. Ceux qui auront anticipé la substitution seront en pôle position.",
    "source": "FiercePharma",
    "source_url": "https://www.fiercepharma.com/pharma/novos-semaglutide-losing-patent-protection-indian-drugmakers-set-launch-their-generics",
    "tiktok_url": "",
    "badge_label": "Pharma Monde",
    "pexels_query": "medicine pills pharmaceutical"
  },
  {
    "id": "actu_2026_03_23_3",
    "date": "2026-03-23",
    "type": "actu",
    "categorie": "sante",
    "titre": "Méningite : 34 cas en Angleterre, vigilance renforcée au comptoir",
    "resume": "L'épidémie de méningocoque en Angleterre s'étend (34 cas, 2 décès). Un décès en France à La Hague. Anticipez les demandes de vaccination et les questions des patients.",
    "full_text": "Épidémie de méningocoque en Angleterre : 34 cas confirmés, 2 décès. L'épisode a démarré dans une discothèque de Canterbury et s'étend. 5 800 vaccinations déjà réalisées dans le Kent.\n\nEn France, un décès par méningite a été signalé à La Hague (salariée d'Orano). 50 cas contacts sous surveillance, pas de lien établi avec le cluster anglais. Mais la proximité géographique impose une vigilance.\n\nCe que ça change au comptoir : attendez-vous à une hausse des demandes de vaccination anti-méningococcique, surtout chez les 16-24 ans et les parents. Vérifiez vos stocks de Nimenrix et Bexsero. Rappel : la vaccination méningocoque C est obligatoire chez le nourrisson, et le B est recommandé.\n\nSignaux d'alerte à connaître pour orienter en urgence : fièvre brutale, céphalées intenses, raideur de nuque, purpura (taches rouges/violacées ne s'effaçant pas à la vitropression). Délai d'action : quelques heures.\n\nEn cas de question d'un patient sur un voyage au Royaume-Uni : recommander la vaccination si non à jour, surtout pour les jeunes adultes fréquentant des lieux de rassemblement.",
    "source": "Le Monde",
    "source_url": "https://www.lemonde.fr/international/article/2026/03/21/epidemie-de-meningites-en-angleterre-le-nombre-de-cas-repertories-monte-a-34_6673262_3210.html",
    "tiktok_url": "",
    "badge_label": "Sante",
    "pexels_query": "vaccination nurse young people"
  },
  {
    "id": "lsv_2",
    "date": "2026-03-23",
    "type": "lsv",
    "categorie": "lsv",
    "titre": "Le saviez-vous ? La croix verte, une obligation réglementaire depuis 1984",
    "resume": "Du caducée à la croix verte : pourquoi le droit international a imposé le changement. Ce que dit le CSP sur l'enseigne officinale.",
    "full_text": "La croix verte, tu la vois clignoter devant ton officine chaque jour. Mais connais-tu le cadre réglementaire derrière ce symbole ?\n\nHistoriquement, la pharmacie utilisait la croix rouge. Problème : les Conventions de Genève de 1949 réservent la croix rouge au Comité international de la Croix-Rouge et aux services de santé des armées. Son usage par les pharmacies était donc illégal au regard du droit international humanitaire.\n\nL'arrêté du 24 juillet 1984 a tranché : la croix verte équilatérale lumineuse devient le signe distinctif obligatoire des officines en France. Le caducée (coupe d'Hygie et serpent d'Asclépios) reste le symbole de la profession mais n'est pas obligatoire en façade.\n\nLe CSP (art. R5125-38 et suivants) encadre strictement l'enseigne : seule la dénomination \"Pharmacie\" et la croix verte sont autorisées. Pas de publicité, pas de nom commercial fantaisiste.\n\nPoint pratique : la croix verte avec affichage température/heure n'a aucune obligation légale d'exactitude, mais c'est devenu un réflexe pour les passants. Certaines ARS ont rappelé à l'ordre des officines dont la croix affichait des températures délirantes.\n\nUn symbole banal en apparence, mais qui engage ta responsabilité professionnelle.",
    "source": "Pharm'Alpha",
    "source_url": "",
    "tiktok_url": "",
    "badge_label": "Le Saviez-Vous",
    "pexels_query": "pharmacy green cross sign"
  },
  {
    "id": "actu_2026_w12_1",
    "date": "2026-03-22",
    "type": "actu",
    "categorie": "pharma_france",
    "titre": "Municipales 2026 : les déserts médicaux au coeur du scrutin",
    "resume": "De 25 000 à 19 000 pharmacies en 25 ans. Le Sénat vote une loi pour les petites communes. Les candidats promettent, on verra bien si ça tient...",
    "full_text": "Les municipales 2026, c'est ce week-end. Premier tour dimanche 15 mars, et LA question qui revient partout dans les campagnes : les déserts médicaux.\n\nEn 25 ans, on est passés de 25 000 à 19 000 pharmacies en France. 6 000 officines disparues. Et ce sont les zones rurales qui trinquent en premier.\n\nLe Sénat a voté une loi pour permettre l'ouverture de pharmacies dans les communes de moins de 2 500 habitants. Les maires s'en emparent : locaux municipaux mis à disposition, aides à l'installation, partenariats avec les maisons de santé.\n\nEst-ce que ça va changer quelque chose ? On verra après le second tour. Mais une chose est sûre : la pharmacie d'officine est devenue un argument électoral. Si ça peut servir à sauver quelques officines, tant mieux.",
    "source": "Public Senat / Le Moniteur",
    "source_url": "https://www.publicsenat.fr",
    "tiktok_url": "",
    "badge_label": "Pharma France",
    "pexels_query": "rural village pharmacy france"
  },
  {
    "id": "actu_2026_w12_2",
    "date": "2026-03-22",
    "type": "actu",
    "categorie": "pharma_france",
    "titre": "Code de déontologie : la refonte qui change tout (ou presque)",
    "resume": "Première mise à jour depuis 1995 ! Tu peux enfin communiquer publiquement sur la santé. Et le charlatanisme, c'est officiellement dans le viseur.",
    "full_text": "Le code de déontologie des pharmaciens vient de faire peau neuve. Première refonte depuis 1995 — oui, 30 ans. Autant dire qu'il était temps.\n\nCe qui change pour toi concrètement :\n\nCommunication publique : tu peux désormais parler de santé publiquement. Réseaux sociaux, médias, conférences. À condition de rester factuel et de ne pas faire de pub déguisée. C'est une petite révolution pour nous qui étions muselés.\n\nIndépendance : le code renforce ta protection face aux pressions commerciales. Groupements, chaînes, tu gardes ton libre arbitre professionnel.\n\nCharlatanisme : nouvelles dispositions contre la vente de produits aux allégations bidon. Tu as maintenant une obligation active de mise en garde.\n\nViolences : tu es officiellement reconnu comme acteur de premier plan pour le repérage des victimes de violences conjugales et familiales.\n\nBref, un code modernisé qui ancre le pharmacien dans son rôle de professionnel de santé de premier recours. Il était temps.",
    "source": "CNOP / Legifrance",
    "source_url": "https://www.ordre.pharmacien.fr",
    "tiktok_url": "",
    "badge_label": "Pharma France",
    "pexels_query": "pharmacist professional white coat"
  },
  {
    "id": "actu_2026_w12_3",
    "date": "2026-03-22",
    "type": "actu",
    "categorie": "pharma_france",
    "titre": "ANSM : essais cliniques en 14 jours, la France accélère enfin",
    "resume": "L'ANSM lance un fast-track pour les essais cliniques : 14 jours au lieu de plusieurs mois. L'objectif : faire de la France un leader européen de la recherche.",
    "full_text": "L'ANSM vient de lancer son dispositif fast-track pour les essais cliniques. Depuis le 16 mars, les autorisations peuvent tomber en 14 jours. Contre plusieurs mois avant.\n\nPourquoi c'est important ? La France était à la traîne face au UK, l'Allemagne et les Pays-Bas en termes de délais. Résultat : les labos allaient tester leurs molécules ailleurs. Pas ouf pour l'écosystème de recherche français.\n\nPour l'instant, ça concerne les essais de phase I et II, plus les médicaments de thérapie innovante. La phase III suivra d'ici la fin de l'année.\n\nPour les pharmaciens hospitaliers, c'est une bonne nouvelle : plus d'essais cliniques = plus d'activité dans les PUI. Et pour les patients, un accès plus rapide aux traitements innovants.\n\nOn croise les doigts pour que ça se concrétise vraiment et que ce ne soit pas qu'un effet d'annonce.",
    "source": "ANSM",
    "source_url": "https://ansm.sante.fr",
    "tiktok_url": "",
    "badge_label": "Pharma France",
    "pexels_query": "clinical trial laboratory research"
  },
  {
    "id": "lsv_3",
    "date": "2026-03-22",
    "type": "lsv",
    "categorie": "lsv",
    "titre": "Le saviez-vous ? De la contamination accidentelle aux bêta-lactamines",
    "resume": "Fleming, Penicillium notatum et la naissance des antibiotiques. 200 millions de vies sauvées, et aujourd'hui l'antibiorésistance menace tout l'édifice.",
    "full_text": "Septembre 1928, hôpital St Mary de Londres. Alexander Fleming rentre de vacances et découvre une contamination par Penicillium notatum dans ses cultures de staphylocoques. Zone d'inhibition nette autour de la moisissure. Il vient de découvrir le premier antibiotique.\n\nMais Fleming n'avait ni les moyens ni les compétences galéniques pour en faire un médicament. Il faudra 12 ans et le travail de Howard Florey et Ernst Boris Chain (Oxford) pour isoler, purifier et stabiliser la pénicilline G. Premier essai clinique en 1941.\n\nLa production industrielle démarre en 1943, juste à temps pour le Débarquement. La pénicilline sauve des milliers de soldats d'infections post-traumatiques qui étaient jusqu'ici fatales.\n\nAujourd'hui, les bêta-lactamines (pénicillines, céphalosporines, carbapénèmes) représentent plus de 60% des prescriptions d'antibiotiques en ville. On estime que les antibiotiques ont sauvé plus de 200 millions de vies.\n\nMais l'édifice est menacé. L'antibiorésistance tue déjà 1,3 million de personnes/an dans le monde. Au comptoir, chaque dispensation d'antibiotique est l'occasion de rappeler les règles : durée de traitement complète, pas de partage, pas d'automédicament. La lutte contre l'antibiorésistance commence à l'officine.",
    "source": "Pharm'Alpha",
    "source_url": "",
    "tiktok_url": "",
    "badge_label": "Le Saviez-Vous",
    "pexels_query": "penicillin antibiotic petri dish"
  },
  {
    "id": "actu_2026_w12_4",
    "date": "2026-03-21",
    "type": "actu",
    "categorie": "sante",
    "titre": "Mars Bleu : tes kits de dépistage gratuits sont arrivés",
    "resume": "47 000 cas de cancer colorectal par an, 17 000 décès. Moins de 30% de dépistage. Les nouveaux kits gratuits sont en pharmacie. À toi de jouer.",
    "full_text": "C'est Mars Bleu, le mois du dépistage du cancer colorectal. Et les chiffres sont flippants.\n\n47 000 nouveaux cas par an. 17 000 décès. Deuxième cancer le plus meurtrier en France. Et pourtant, moins de 30% des 50-74 ans se font dépister. Moins d'un sur trois.\n\nLes nouveaux kits sont dispos dans ton officine depuis le 15 mars. Gratuits, sans ordonnance, résultat en quelques jours. Un prélèvement de selles à domicile, envoi par courrier, et voilà.\n\nDétecté tôt, ce cancer se guérit dans 9 cas sur 10. Neuf sur dix. Si c'est pas un argument de poids au comptoir, je sais pas ce qu'il te faut.\n\nChaque patient de plus de 50 ans qui entre chez toi, c'est une occasion de lui en parler. Ça prend 30 secondes. Et ça peut littéralement sauver une vie.",
    "source": "VIDAL / INCa",
    "source_url": "https://www.vidal.fr",
    "tiktok_url": "",
    "badge_label": "Sante",
    "pexels_query": "cancer screening medical checkup"
  },
  {
    "id": "actu_2026_w12_5",
    "date": "2026-03-21",
    "type": "actu",
    "categorie": "pharma_france",
    "titre": "PharmagoraPlus 2026 : IA, e-ordonnance et crise du modèle",
    "resume": "12 000 pharmaciens à Paris. Les sujets chauds : l'IA au comptoir, l'ordonnance numérique, la carte Vitale dématérialisée et... la survie économique de l'officine.",
    "full_text": "PharmagoraPlus 2026, c'était les 14 et 15 mars à Porte de Versailles. Plus de 12 000 professionnels réunis. Voici ce qu'il fallait retenir.\n\nL'IA débarque au comptoir. Plusieurs startups ont montré des outils d'aide à la dispensation, détection d'interactions, optimisation des stocks. C'est plus du gadget, c'est du concret.\n\nL'e-ordonnance s'accélère. Objectif : 100% dématérialisé d'ici fin 2027. Les éditeurs de logiciels ont montré leurs solutions. Fini le papier griffonné illisible ? On y croit.\n\nCarte Vitale numérique. Après les expérimentations dans plusieurs départements, le déploiement national est confirmé pour 2027. La carte physique ne disparaîtra pas, mais deviendra secondaire.\n\nEt LE sujet qui fâche : le modèle économique. Marges en baisse, charges en hausse. Quel avenir pour l'officine ? Les intervenants ont plaidé pour une revalorisation des actes. On attend de voir.\n\nBref, un salon qui confirme que notre métier est en pleine mutation. Le train est en marche, autant être dedans.",
    "source": "PharmagoraPlus",
    "source_url": "https://www.pharmagoraplus.com",
    "tiktok_url": "",
    "badge_label": "Pharma France",
    "pexels_query": "pharmacy conference trade show"
  },
  {
    "id": "lsv_4",
    "date": "2026-03-21",
    "type": "lsv",
    "categorie": "lsv",
    "titre": "Le saviez-vous ? Le NAPQI, métabolite tueur du paracétamol",
    "resume": "1ère cause de greffe hépatique en France. Le mécanisme de toxicité par saturation du glutathion, et les réflexes de dispensation pour prévenir le surdosage.",
    "full_text": "Le paracétamol est la première cause d'insuffisance hépatique aiguë et de greffe du foie en France. Plus que l'alcool. Et c'est le médicament qu'on dispense le plus.\n\nLe mécanisme est bien connu : à dose thérapeutique, 90% du paracétamol est métabolisé par glucurono- et sulfoconjugaison hépatique. Les 10% restants passent par le CYP2E1 et produisent le NAPQI (N-acétyl-p-benzoquinone imine), un métabolite hautement réactif. Le glutathion le neutralise. Mais au-delà de 3-4g/jour, les réserves de glutathion s'épuisent. Le NAPQI s'accumule et détruit les hépatocytes.\n\nLe piège : la fenêtre asymptomatique. Le patient se sent bien pendant 24 à 48h après un surdosage. Quand les symptômes hépatiques apparaissent, les dégâts sont souvent irréversibles. L'antidote (N-acétylcystéine IV) doit être administré dans les 8-10h.\n\nAu comptoir, les réflexes essentiels : vérifier systématiquement les associations (combien de spécialités contiennent du paracétamol caché ?), alerter sur le cumul Doliprane + Efferalgan + Dafalgan (même DCI, les patients ne le savent pas toujours), et adapter la posologie chez l'insuffisant hépatique et l'alcoolique chronique.\n\nDepuis 2020, les boîtes portent un message d'alerte. Mais c'est au comptoir que la prévention est la plus efficace.",
    "source": "Pharm'Alpha",
    "source_url": "",
    "tiktok_url": "",
    "badge_label": "Le Saviez-Vous",
    "pexels_query": "paracetamol acetaminophen pills"
  },
  {
    "id": "lsv_5",
    "date": "2026-03-20",
    "type": "lsv",
    "categorie": "lsv",
    "titre": "Le saviez-vous ? Angine et cystite : la prescription pharmaceutique en pratique",
    "resume": "Depuis 2024, TROD + prescription d'antibiotiques en officine. Retour sur le cadre légal, la rémunération et les premiers bilans chiffrés.",
    "full_text": "Depuis 2024, tu peux prescrire et délivrer des antibiotiques pour l'angine à streptocoque et la cystite simple. Une évolution majeure du périmètre officinal, encadrée par le décret du 18 juin 2024.\n\nLe parcours angine : TROD strepto A au comptoir. Si positif, prescription d'amoxicilline (ou azithromycine si allergie). Rémunération : 6,50 EUR par TROD + honoraire de dispensation. Premier bilan : plus de 800 000 TROD réalisés en officine sur les 6 premiers mois.\n\nLe parcours cystite : questionnaire structuré (femme 16-65 ans, pas de signes de complication, pas enceinte), BU au comptoir, puis prescription de fosfomycine-trométamol en dose unique. Rémunération identique.\n\nCe qui change fondamentalement : tu engages ta responsabilité de prescripteur. Traçabilité obligatoire dans le DP, information au médecin traitant, respect strict des arbres décisionnels. Les cas hors critères doivent être réorientés.\n\nLes chiffres montrent que les patients adoptent massivement le dispositif. 6 millions de Français sans médecin traitant, urgences saturées : l'officine devient le premier point de contact santé. Les prochaines étapes ? Potentiellement la conjonctivite bactérienne et les infections urinaires masculines simples.",
    "source": "Pharm'Alpha",
    "source_url": "",
    "tiktok_url": "",
    "badge_label": "Le Saviez-Vous",
    "pexels_query": "pharmacist patient consultation counter"
  }
]


# ============================================================
# PEXELS PHOTO DOWNLOAD
# ============================================================
def search_pexels(query, orientation="landscape"):
    """Search Pexels for a photo, return landscape URL or None."""
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": PEXELS_KEY}
    params = {"query": query, "per_page": 1, "orientation": orientation}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("photos"):
            return data["photos"][0]["src"]["landscape"]  # 1200x627
    except Exception as e:
        print(f"  [WARN] Pexels search failed for '{query}': {e}")
    return None


def download_photo(url, filepath):
    """Download a photo to filepath."""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print(f"  [WARN] Download failed: {e}")
        return False


# ============================================================
# BUILD JS ARTICLES ARRAY
# ============================================================
def escape_js(s):
    """Escape a string for JS."""
    return (s
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def build_js_articles(articles_with_images):
    """Build the JS const ARTICLES = [...] string."""
    lines = ["const ARTICLES = ["]
    for i, a in enumerate(articles_with_images):
        lines.append("  {")
        lines.append(f'    id: "{a["id"]}",')
        lines.append(f'    date: "{a["date"]}",')
        lines.append(f'    type: "{a["type"]}",')
        lines.append(f'    categorie: "{a["categorie"]}",')
        lines.append(f'    titre: "{escape_js(a["titre"])}",')
        lines.append(f'    resume: "{escape_js(a["resume"])}",')
        lines.append(f'    full_text: "{escape_js(a["full_text"])}",')
        lines.append(f'    source: "{escape_js(a["source"])}",')
        lines.append(f'    source_url: "{a["source_url"]}",')
        lines.append(f'    tiktok_url: "{a["tiktok_url"]}",')
        lines.append(f'    badge_label: "{a["badge_label"]}",')
        lines.append(f'    image_url: "{a.get("image_url", "")}"')
        comma = "," if i < len(articles_with_images) - 1 else ""
        lines.append("  }" + comma)
    lines.append("];")
    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================
def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # 1. Download Pexels photos for all articles
    print("=== Downloading Pexels photos ===")
    for a in ARTICLES:
        article_id = a["id"]
        query = a.get("pexels_query", "pharmacy")
        img_path = os.path.join(ASSETS_DIR, f"img_{article_id}.jpg")

        if os.path.exists(img_path):
            print(f"  [SKIP] {article_id} already has .jpg")
            a["image_url"] = f"assets/img_{article_id}.jpg"
            continue

        print(f"  [{article_id}] Searching '{query}'...")
        photo_url = search_pexels(query)
        if photo_url:
            if download_photo(photo_url, img_path):
                a["image_url"] = f"assets/img_{article_id}.jpg"
                print(f"    -> Downloaded OK")
            else:
                a["image_url"] = ""
                print(f"    -> Download FAILED")
        else:
            a["image_url"] = ""
            print(f"    -> No result from Pexels")

        time.sleep(0.3)  # Rate limit

    # 2. Build new JS
    print("\n=== Building new ARTICLES array ===")
    js_articles = build_js_articles(ARTICLES)

    # 3. Update index.html
    print("=== Updating index.html ===")
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace the ARTICLES block
    pattern = r'const ARTICLES = \[.*?\];'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        print("[ERROR] Could not find ARTICLES array in index.html!")
        return

    html = html[:match.start()] + js_articles + html[match.end():]

    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n=== Done! {len(ARTICLES)} articles written ===")
    print(f"  - 4 articles for 2026-03-25 (3 actus + 1 LSV)")
    print(f"  - 4 articles for 2026-03-24 (3 actus + 1 LSV)")
    print(f"  - 4 articles for 2026-03-23 (3 actus + 1 LSV)")
    print(f"  - 4 articles for 2026-03-22 (3 actus + 1 LSV)")
    print(f"  - 3 articles for 2026-03-21 (2 actus + 1 LSV)")
    print(f"  - 1 article  for 2026-03-20 (1 LSV)")


if __name__ == "__main__":
    main()
