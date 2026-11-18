from __future__ import annotations

import argparse
import re
import subprocess
import sys
import json
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--local-url', default='http://localhost:8787')
    parser.add_argument('--discord-webhook-file', default='')
    parser.add_argument('--cloudflared', default='cloudflared')
    args = parser.parse_args()
    try:
        token = Path(args.token_file).read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError) as exc:
        print(f'Zugriffsschlüssel konnte nicht gelesen werden: {exc}')
        return 1
    if not token:
        print('Kein Zugriffsschlüssel gefunden. Zuerst Starten.bat ausführen.')
        return 1
    try:
        process = subprocess.Popen([args.cloudflared, 'tunnel', '--url', args.local_url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except OSError as exc:
        print(f'cloudflared konnte nicht gestartet werden: {exc}')
        return 1
    print('HTTPS-Tunnel wird gestartet ...')
    public = None
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end='')
        match = URL_RE.search(line)
        if match:
            public = f'{match.group(0)}/?key={quote(token, safe="")}'
            print('\nFREIGABE-LINK FUER FREUNDE:')
            print(public)
            print('\nDiesen Link komplett teilen. Der Zugriffsschluessel ist im Link enthalten.')
            if args.discord_webhook_file:
                webhook_path = Path(args.discord_webhook_file)
                if webhook_path.is_file():
                    webhook = webhook_path.read_text(encoding='utf-8').strip()
                    if webhook and not webhook.startswith('HIER_'):
                        # TEXT GEÃ„NDERT: Zeigt jetzt NNBW Videoarchiv in Discord an
                        payload = json.dumps({'content': f'NNBW Videoarchiv ist online. Geschuetzter Link:\n{public}'}).encode('utf-8')
                        
                        # KORREKTUR: Browser-User-Agent hinzugefügt, um HTTP 403 Blockaden bei Discord zu umgehen
                        headers = {
                            'Content-Type': 'application/json',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                        }
                        request = urllib.request.Request(webhook, data=payload, headers=headers, method='POST')
                        try:
                            with urllib.request.urlopen(request, timeout=15) as response:
                                if 200 <= response.status < 300:
                                    print('Der geschuetzte Link wurde automatisch in Discord gepostet.')
                                else:
                                    print(f'Discord hat den Link nicht angenommen (HTTP {response.status}).')
                        except urllib.error.HTTPError as exc:
                            if exc.code == 403:
                                print('Discord-Webhook wurde abgelehnt (HTTP 403). Falls der Webhook neu ist, schlieÃŸe dieses Fenster und starte Freigabe starten.bat einfach neu.')
                            elif exc.code in {401, 404}:
                                print(f'Discord-Webhook ist nicht gueltig (HTTP {exc.code}). Einen neuen Webhook erstellen und die URL ersetzen.')
                            else:
                                print(f'Discord-Versand fehlgeschlagen (HTTP {exc.code}).')
                        except Exception as exc:
                            print(f'Discord-Versand fehlgeschlagen: {exc}')
                    else:
                        print('Discord-Webhook-Datei ist noch nicht eingerichtet; Link wurde nicht gepostet.')
                else:
                    print('discord_webhook.txt fehlt; Link wurde nicht gepostet.')
            try:
                subprocess.run(['clip'], input=public, text=True, check=False)
                print('Der Link wurde in die Windows-Zwischenablage kopiert.')
            except OSError:
                pass
            print('Dieses Fenster offen lassen. Zum Beenden Strg+C druecken.')
            break
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 0
    return process.returncode or 0


if __name__ == '__main__':
    sys.exit(main())
