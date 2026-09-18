# Isdhine
**"I see you. I protect you."**

Isdhine est un outil de sécurité et de confidentialité qui utilise la webcam de l'ordinateur pour détecter la présence de l'utilisateur et verrouiller l'ordinateur en cas d'absence.
Il respecte la vie privée : le traitement se fait à 100% en local et le flux vidéo n'est jamais sauvegardé ni envoyé.

## Installation

### Windows
Créez l'environnement virtuel, installez les dépendances, puis lancez avec :
```cmd
run_isdhine.bat
```

### Linux
📖 Un guide détaillé pas à pas (prérequis, dépannage, webcam) est disponible dans **[INSTALL-LINUX.md](INSTALL-LINUX.md)**.

Installation en une seule fois :
```bash
# 1. Prérequis système (exemple Debian/Ubuntu)
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libgl1 libxcb-cursor0 xdg-utils

# 2. Récupérer le projet
git clone https://github.com/123Asoumi/faceid.git
cd faceid

# 3. Environnement virtuel + dépendances
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```
> Fedora : `sudo dnf install -y git python3 python3-pip xdg-utils mesa-libGL`
> Arch : `sudo pacman -S git python python-pip xdg-utils`

## Lancer l'application

### Windows
```cmd
run_isdhine.bat
```

### Linux
À chaque utilisation, il suffit de :
```bash
cd faceid
./run_bloqz.sh
```
Le script `run_bloqz.sh` active automatiquement l'environnement et démarre l'application.

## Raccourci de bureau (Linux)
Pour ajouter BLOQZ au menu des applications et sur le bureau (avec icône), lancez une fois :
```bash
chmod +x install-desktop.sh
./install-desktop.sh
```
Ensuite l'application se lance d'un simple clic, sans terminal.
Pour retirer le raccourci : `./install-desktop.sh --uninstall`

## Fonctionnalités
- Verrouillage automatique de l'ordinateur en l'absence de l'utilisateur.
- Configurable : délai d'absence, choix de webcam.
- Mode discret (Monochrome, design minimaliste et tray system).
- Confidentialité garantie : aucun cloud, tout se passe sur votre machine.

## Source
Inspiré par [Lock on Absence](https://github.com/handnewb/lock-on-absence).
Isdhine inclut un MVP recréant les composants et la logique, basé sur un modèle de détection de visage Haar cascades intégré.
