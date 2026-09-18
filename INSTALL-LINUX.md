# Guide d'installation — Linux

Ce guide explique comment installer et lancer **BLOQZ / Isdhine** sur Linux,
de A à Z, avec la résolution des problèmes les plus fréquents.

> BLOQZ utilise la webcam pour détecter votre présence et verrouiller
> l'ordinateur en cas d'absence. Tout le traitement est **100 % local** :
> aucune image n'est enregistrée ni envoyée.

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

## 8. Désinstaller

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
# prérequis (Debian/Ubuntu)
sudo apt install -y git python3 python3-venv python3-pip libgl1 libglib2.0-0 \
    libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 xdg-utils

# installation
git clone https://github.com/123Asoumi/faceid.git
cd faceid
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt

# lancement
./run_bloqz.sh

# raccourci de bureau (optionnel)
chmod +x install-desktop.sh && ./install-desktop.sh
```
