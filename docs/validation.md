# Vérification de la version autonome

Vérifications locales du 21 octobre 2026, Windows, Python 3.12.13. Ces contrôles concernent la démo et le paquet extraits ; les grandes mesures historiques restent dans les autres documents.

- 27 tests Python : base de démonstration séparée, noms/lieux/fantasy, romanisation, bulk, catalogue, validation HTTP, reconstruction dans un nouveau fichier et protection des bases existantes.
- Parcours Edge sans interface : génération de noms et lieux, téléchargement JSON, captures desktop/mobile, absence d'erreurs JavaScript et de débordement horizontal à 390 px.
- Construction wheel/sdist ; installation du wheel dans un environnement vierge hors du checkout, données et ressources web embarquées.
- La base mondiale existante reste locale et séparée ; elle n'est pas nécessaire à ces contrôles.

Reproduire avec les commandes de README.md. Le serveur est une démo locale ; aucun hébergement public n'est configuré.
