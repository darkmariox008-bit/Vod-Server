# Performance-Version

Diese Variante enthält ausschließlich Verbesserungen für Laufzeit, Netzwerkverbrauch, Browser-Caching und Wartbarkeit der Performance-relevanten Stellen. Die grundlegenden Funktionen des VOD-/HLS-Servers bleiben unverändert.

## Enthaltene Performance-Verbesserungen

### Server

- Der Playlist- und Videoordner-Scan wird höchstens alle drei Sekunden erneut ausgeführt. Ein erzwungenes Neuladen über den Admin-Bereich bleibt möglich.
- HTML bleibt aktuell und wird nicht gecachet.
- Statische CSS-, JavaScript- und Bibliotheksdateien werden für eine Stunde im Browser gecachet. Dadurch werden wiederholte Downloads beim Öffnen oder Aktualisieren reduziert.

### HLS-Wiedergabe

- Die Wiedergabe ist auf VOD-HLS ausgelegt, statt unnötige Live-HLS-Einstellungen zu verwenden.
- Der Puffer ist größer, damit entfernte oder mobile Geräte weniger häufig nachladen müssen.
- Der Rückpuffer wird begrenzt, um Speicherverbrauch zu kontrollieren.
- Wiederholungsversuche bei HLS-Netzwerkfehlern wurden von sechs auf vier reduziert. Dadurch werden Fehler schneller sichtbar und es entstehen weniger lang anhaltende Wiederholungsanfragen.

### Browser-Anfragen

- Die globale Synchronisationsabfrage läuft alle zwei Sekunden statt jede Sekunde.
- Latenzmessungen laufen alle zehn statt alle fünf Sekunden.
- Die Vorschau wird alle 15 statt alle zehn Sekunden aktualisiert.
- Bei nicht sichtbaren Browser-Tabs werden diese regelmäßigen Abfragen pausiert.

### Kleine Laufzeitbereinigungen

- Videodateiendungen werden beim Anzeigen nur noch am Dateiende entfernt.
- Eine doppelte JavaScript-Zuweisung wurde entfernt.

## Bewusst nicht verändert

- Keine neuen Funktionen.
- Keine Änderung am Playlist-Konzept.
- Keine Änderung am Freigabeablauf.
- Keine Umstellung der Authentifizierung in dieser Performance-Version.
- Keine Änderung an Videoqualität, Auflösung oder HLS-Ladder-Erzeugung.

## Hinweis für GitHub

Die persönlichen Laufzeitdateien `.vod_access_token.txt` und `discord_webhook.txt` sind nicht Bestandteil dieser GitHub-Kopie. Eine Vorlage für den optionalen Discord-Webhook liegt als `discord_webhook.txt.example` bei. Persönliche Werte bitte nur lokal eintragen und nicht hochladen.
