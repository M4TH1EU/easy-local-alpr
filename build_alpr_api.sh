pyinstaller --noconfirm --console --add-data libs:. --add-data assets:assets --add-data static:static --add-data templates:templates --name easy-local-alpr-1.4.0-openvinocpu_linux_x86_64 "alpr_api.py"
# optional: --onefile