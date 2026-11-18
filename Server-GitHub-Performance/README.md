# VOD/HUB – Performance-Version

Diese ZIP enthält eine für GitHub vorbereitete Version des VOD-/HLS-Servers mit ausschließlich performancebezogenen Anpassungen. Die genaue Änderungsliste steht in [PERFORMANCE.md](PERFORMANCE.md).

## Schnellstart unter Windows

1. Den Ordner vollständig herunterladen und entpacken.
2. Python 3.10 oder neuer sowie FFmpeg und FFprobe installieren.
3. In `Starten.bat` den Pfad `VOD_FOLDER` anpassen oder eine lokale Datei `.vod_folder.txt` mit dem Pfad zum Videoordner anlegen.
4. `Starten.bat` doppelt anklicken.
5. Für eine öffentliche Freigabe kann anschließend `Freigabe starten.bat` verwendet werden, wenn Cloudflared lokal installiert ist.

## GitHub-Upload

Auf GitHub ein neues Repository erstellen, die ZIP lokal entpacken und im entpackten Ordner alle Dateien hochladen. Die Datei `.gitignore` verhindert, dass lokale Tokens, Webhooks, Thumbnails und HLS-Ausgabedateien versehentlich versioniert werden.

Die Dateien `.vod_access_token.txt` und `discord_webhook.txt` sind absichtlich nicht enthalten. Sie werden lokal beim Start eingerichtet. Die mitgelieferte Datei `discord_webhook.txt.example` ist nur eine Vorlage und enthält kein persönliches Geheimnis.

## Projektdateien

`local_vod_server.py` ist der lokale HTTP-/VOD-Server. `website/` enthält die Oberfläche und den Player. `vod_convert.py` konvertiert MKV/WebM-Dateien, `make_hls_ladder.py` erzeugt optionale HLS-Varianten und `public_link.py` startet die optionale Cloudflare-Freigabe.

## Umfang dieser Version

Diese Ausgabe ist ausdrücklich eine Performance-Version. Sie verändert nicht das grundsätzliche Bedienkonzept und nimmt keine Funktionsausweitung vor. Die technische Sicherheitsüberarbeitung ist ein separates Thema und wurde hier nicht als Performance-Änderung umgesetzt.
