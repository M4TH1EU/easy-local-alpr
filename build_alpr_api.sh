#!/bin/bash

VERSION=1.5.0

rm -rf buildenv build dist *.spec
python3.10 -m venv buildenv
source buildenv/bin/activate
python3.10 -m pip install --upgrade pip pyinstaller
python3.10 -m pip install ./wheel/ultimateAlprSdk-3.0.0-cp310-cp310-linux_x86_64.whl
pip install -r requirements.txt

pyinstaller --noconfirm --onefile --console --add-data libs:. --add-data assets:assets --add-data static:static --add-data templates:templates --name easy-local-alpr-$VERSION-openvinocpu_linux_x86_64 "alpr_api.py"
deactivate
rm -rf buildenv