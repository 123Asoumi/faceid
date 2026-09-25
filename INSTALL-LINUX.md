# Guide d'installation — Linux

Ce guide explique comment installer et lancer **BLOQZ / Isdhine** sur Linux,
de A à Z, avec la résolution des problèmes les plus fréquents.

> BLOQZ utilise la webcam pour détecter votre présence et verrouiller
> l'ordinateur en cas d'absence. Tout le traitement est **100 % local** :
> aucune image n'est enregistrée ni envoyée.

---

## ⚡ Installation en 3 commandes (SSH)

Pour les personnes pressées. Prérequis : avoir installé les paquets système
(voir §1) **une seule fois**, et disposer d'une **clé SSH liée à GitHub**
(voir §1 bis).

```bash
# 1) Cloner le dépôt et entrer dedans
git clone git@github.com:123Asoumi/faceid.git && cd faceid

# 2) Créer l'environnement et installer les dépendances
python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

# 3) Créer l'icône sur le bureau + dans le menu des applications
chmod +x install-desktop.sh && ./install-desktop.sh
```

Après la 3ᵉ commande, **BLOQZ apparaît dans le menu des applications et sur le
bureau** : lancez-le d'un simple clic (sous GNOME, au premier lancement :
clic droit → « Autoriser le lancement »).

> 💡 Vous préférez lancer en ligne de commande ? Utilisez `./run_bloqz.sh`
> à la place de la 3ᵉ commande. Les fois suivantes : `cd faceid && ./run_bloqz.sh`.

> 💡 Pas de clé SSH ? Utilisez l'URL HTTPS à la place à l'étape 1 :
> `git clone https://github.com/123Asoumi/faceid.git && cd faceid`

---

## 1. Prérequis système

Il faut Python 3, `git`, l'outil `venv`, ainsi que quelques bibliothèques
système pour Qt (l'interface) et OpenGL.

**Debian / Ubuntu / Mint / Pop!_OS**
```bash
sudo apt update
sudo apt install -y \
    git python3 python3-venv python3-pip \
    libgl1 libglib2.0-0 \
    libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 \
    xdg-utils
```

**Fedora**
```bash
sudo dnf install -y git python3 python3-pip xdg-utils \
    mesa-libGL xcb-util-cursor libxkbcommon-x11
```

**Arch / Manjaro**
```bash
sudo pacman -S --needed git python python-pip xdg-utils \
    mesa xcb-util-cursor libxkbcommon-x11
```

> Les paquets `libxcb-cursor0` / `xcb-util-cursor` sont nécessaires depuis
> Qt 6.5 pour l'affichage via X11. Sans eux, l'app peut refuser de démarrer.

### 1 bis. Configurer une clé SSH pour GitHub (pour le clone SSH)

Nécessaire uniquement si vous clonez avec `git@github.com:...`. Sinon, sautez
cette étape et utilisez l'URL HTTPS.

```bash
# Générer une clé (si vous n'en avez pas déjà une)
ssh-keygen -t ed25519 -C "votre_email@example.com"
# (appuyez sur Entrée pour accepter les valeurs par défaut)

# Afficher la clé PUBLIQUE à copier
cat ~/.ssh/id_ed25519.pub
```

Copiez la ligne affichée, puis ajoutez-la sur GitHub :
**Settings → SSH and GPG keys → New SSH key** (https://github.com/settings/keys).

Vérifiez que la connexion fonctionne :
```bash
ssh -T git@github.com
```
Vous devez voir : `Hi <votre_pseudo>! You've successfully authenticated...`

---

## 2. Télécharger le projet

```bash
git clone https://github.com/123Asoumi/faceid.git
cd faceid
```

---

## 3. Environnement virtuel + dépendances

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### ⚠️ Important : version d'OpenCV
L'application nécessite **OpenCV 4.x**. OpenCV 5.0 a retiré l'API des cascades
Haar (`cv2.CascadeClassifier`) utilisée par le détecteur de visage, ce qui
provoque l'erreur :
```
AttributeError: module 'cv2' has no attribute 'CascadeClassifier'
```
Le fichier `requirements.txt` épingle déjà la bonne version
(`opencv-python-headless>=4.8,<5`). Si vous rencontrez malgré tout ce message,
forcez la réinstallation :
```bash
pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python
pip install --no-cache-dir "opencv-python-headless>=4.8,<5"
```

Vérification :
```bash
python3 -c "import cv2; print(cv2.__version__); print(cv2.CascadeClassifier)"
```
La version doit commencer par **4.** et la deuxième ligne doit afficher
`<class 'cv2.CascadeClassifier'>`.

> On utilise `opencv-python-headless` (et non `opencv-python`) car ce dernier
> embarque ses propres bibliothèques Qt qui entrent en conflit avec PySide6 et
> provoquent un crash `Aborted (core dumped)` au démarrage de l'interface.

---

## 4. Lancer l'application

À chaque utilisation :
```bash
cd faceid
./run_bloqz.sh
```

Le script `run_bloqz.sh` :
- active automatiquement l'environnement `.venv` ;
- écrit les éventuelles erreurs dans **`bloqz.log`** ;
- réessaie avec le backend X11 (`xcb`) si le démarrage Wayland échoue.

Équivalent manuel :
```bash
source .venv/bin/activate
python3 isdhine.py
```

---

## 5. Ajouter un raccourci de bureau (recommandé)

Pour lancer BLOQZ d'un simple clic depuis le menu des applications et le bureau :

```bash
chmod +x install-desktop.sh
./install-desktop.sh
```

- L'entrée apparaît dans le **menu des applications** (`BLOQZ`).
- Une icône est aussi copiée sur le **bureau**.
- Sous GNOME, au premier clic il peut falloir faire
  **clic droit → « Autoriser le lancement »**.

Pour retirer le raccourci :
```bash
./install-desktop.sh --uninstall
```

---

## 6. Autoriser l'accès à la webcam

Vérifiez qu'une caméra est détectée :
```bash
ls /dev/video*
```
Si rien ne s'affiche, la webcam n'est pas reconnue par le système. Sur certaines
distributions il faut appartenir au groupe `video` :
```bash
sudo usermod -aG video "$USER"
```
(Déconnectez/reconnectez la session pour appliquer le changement.)

---

## 7. Dépannage

Toutes les erreurs de démarrage sont enregistrées dans **`bloqz.log`** :
```bash
cat bloqz.log
```

| Message | Cause | Solution |
|---|---|---|
| `module 'cv2' has no attribute 'CascadeClassifier'` | OpenCV 5.x installé | Réinstaller en 4.x (voir §3) |
| `Aborted (core dumped)` au lancement de l'UI | Conflit Qt entre `opencv-python` et PySide6 | Utiliser `opencv-python-headless` (voir §3) |
| `Could not load the Qt platform plugin "xcb"` | Lib système manquante | `sudo apt install -y libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0` |
| `libGL.so.1: cannot open shared object file` | OpenGL manquant | `sudo apt install -y libgl1` |
| `ModuleNotFoundError: No module named 'cv2' / 'PySide6'` | `.venv` incomplet ou non activé | `source .venv/bin/activate` puis `pip install -r requirements.txt` |
| L'app ne s'ouvre pas sous Wayland | Backend graphique | Forcer X11 : `QT_QPA_PLATFORM=xcb ./run_bloqz.sh` |
| Aucune caméra | Webcam non détectée / droits | Voir §6 (`ls /dev/video*`, groupe `video`) |

### Forcer le backend graphique
Selon votre session (Wayland ou X11), vous pouvez forcer manuellement :
```bash
QT_QPA_PLATFORM=xcb ./run_bloqz.sh      # forcer X11
QT_QPA_PLATFORM=wayland ./run_bloqz.sh  # forcer Wayland
```

---

## 8. (Option) Créer un exécutable autonome (« .exe » Linux)

Sur Linux, l'équivalent d'un `.exe` est un **binaire exécutable** sans extension.
On le génère avec **PyInstaller** à partir du fichier `BLOQZ.spec` fourni.

```bash
chmod +x build-linux.sh
./build-linux.sh
```

Le binaire est créé dans **`dist/BLOQZ`**. Pour le lancer :
```bash
./dist/BLOQZ
```

Ce binaire embarque Python, les bibliothèques et les assets : il peut être copié
et lancé **sans installer quoi que ce soit** sur la machine cible.

> ⚠️ **Portabilité limitée.** Un binaire PyInstaller n'est pas garanti compatible
> entre distributions ou versions de Linux différentes (la `glibc` du système de
> compilation doit être ≤ celle de la machine cible). Pour une diffusion large :
> - compilez sur la **distribution la plus ancienne** que vous voulez supporter
>   (ex. une vieille Ubuntu LTS), **ou**
> - fournissez plutôt un **AppImage** / **Flatpak** (formats conçus pour être
>   portables), **ou**
> - laissez chaque utilisateur compiler sur sa propre machine avec la commande
>   ci-dessus.

Vous pouvez ensuite pointer le raccourci de bureau vers ce binaire au lieu du
script Python, en remplaçant la ligne `Exec=` du fichier `.desktop` par le chemin
absolu de `dist/BLOQZ`.

---

## 9. Désinstaller

```bash
# retirer le raccourci de bureau
./install-desktop.sh --uninstall

# supprimer le projet et son environnement
cd ..
rm -rf faceid
```

---

## Résumé express

```bash
# prérequis, une seule fois (Debian/Ubuntu)
sudo apt install -y git python3 python3-venv python3-pip libgl1 libglib2.0-0 \
    libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 xdg-utils

# installation en 3 commandes (SSH) — crée aussi l'icône sur le bureau
git clone git@github.com:123Asoumi/faceid.git && cd faceid
python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt
chmod +x install-desktop.sh && ./install-desktop.sh

# (ou pour lancer directement en ligne de commande : ./run_bloqz.sh)
```
