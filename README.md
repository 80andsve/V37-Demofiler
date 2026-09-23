# V37 Utökad, fungerande ärendeformulär

Det här är en utökad variant av v37 (Storage) där Novatrix kundtjänstformulär
faktiskt fungerar. Sidan ligger kvar på webbservern, och när man skickar in ett
ärende sparas det som en blob i containern `arenden`. Skrivningen görs av en
liten backend på VM:en som loggar in med VM:ens system-tilldelade hanterade
identitet, alltså helt utan nyckel i koden.

Mappen är fristående och rör inte de befintliga v37-filerna. Tanken är att den
här grunden är färdig att köra, och att ni bara justerar sina egna
värden (framför allt sitt eget storage-kontonamn).

## Så hänger det ihop

Formuläret är statiskt HTML som nginx serverar, precis som förut. Det nya är att
formuläret nu postar till `/submit`. nginx skickar den vägen vidare till en
Flask-backend som kör lokalt på VM:en (`127.0.0.1:5000`). Backenden tar emot
namn, e-post, meddelande och en eventuell bild, och laddar upp allt till
containern `arenden`.

Poängen med upplägget är identiteten. En sida som ligger i webbläsaren har ingen
identitet, så själva skrivningen måste ske på servern. Backenden använder
`DefaultAzureCredential`, som automatiskt hämtar en token via VM:ens
system-tilldelade identitet (genom IMDS). Eftersom identiteten är ensam behövs
inget client-id, precis det som sägs på identitets-sliden i Del 11A.

## Filer

- `index.html`, formuläret, nu med `action="/submit"`, `method="post"` och `enctype="multipart/form-data"`.
- `app.py`, Flask-backenden som skriver ärendet till Blob via den hanterade identiteten.
- `nginx-arende.conf`, nginx-konfigurationen som serverar sidan och proxar `/submit` till backenden.
- `arendeapp.service`, systemd-enheten som håller backenden igång.
- `cloud-init.txt`, allt ovanstående paketerat, redo att användas som `--custom-data` när webb-VM:en skapas.

## Det som behöver ändras

I `app.py`, längst upp, finns ett markerat block med tre inställningar. Bara
den första måste ändras för att grunden ska fungera, de andra två styr hur
ärendet hanteras vidare:

`STORAGE_ACCOUNT` byts mot ditt eget globalt unika kontonamn (samma konto som
provisioneringen skapade). Behåll `CONTAINER` som `arenden` om du inte döpt om den.

`BLOB_LAYOUT` styr var ärendet hamnar i containern:

- `"root"` (standard) lägger ärendet platt i roten som `arende-<id>.json`. Det
  behövs om du senare ska trigga ett Power Automate-flöde på bloben, eftersom
  Blob-triggern bara ser roten.
- `"folder"` lägger ärendet i en egen mapp per ärende som `<id>/arende.json`.
  Prydligare, men Blob-triggern ser inte undermappar.

`FLOW_URL` lämnas tom så länge du inte har ett flöde. Fyller du i adressen från
en HTTP-trigger i Power Automate ("När en HTTP-förfrågan tas emot") postar appen
ärendet dit direkt efter att bloben skrivits. Anropet är inlindat så att ett
trasigt flöde aldrig stoppar att ärendet sparas.

Ändrar man i `app.py` måste ändringen även in i `cloud-init.txt` (samma kod
ligger inbäddad där), eftersom det är `cloud-init.txt` som driftsätts när VM:en
skapas från grunden.

## Förutsättningar

Innan det här kan skriva något måste tre saker finnas, och det är precis vad
v37-provisioneringen redan sätter upp:

- ett storage-konto och containern `arenden`,
- VM:ens system-tilldelade identitet påslagen (`az vm identity assign`),
- rollen `Storage Blob Data Contributor` tilldelad den identiteten på kontot.

## Driftsätt

Skapa webb-VM:en med den här mappens `cloud-init.txt` som custom-data, i stället
för basversionen. Kärnan i kommandot:

    az vm create \
      --resource-group "$RG" \
      --name "$VM" \
      --image Ubuntu2204 \
      --custom-data cloud-init.txt \
      --nsg "" \
      ...

Skapar du VM:en så här får du hela grunden på plats från start, med de värden du
satt i `cloud-init.txt`.

## Uppdatera bara app.py på en VM som redan kör

Har du redan en körande webb-VM och bara vill ha in den nya app.py (till exempel
för att byta layout eller slå på ett flöde), behöver du inte skapa om VM:en. Byt
ut filen på plats och starta om tjänsten. Välj det sätt du är bekväm med.

### Alternativ A, redigera direkt på VM:en (nano)

Logga in på VM:en (via Bastion eller SSH) och öppna filen:

    sudo nano /opt/arendeapp/app.py

Sätt de tre inställningarna högst upp till dina egna värden:

- `STORAGE_ACCOUNT` till ditt kontonamn (samma som förut).
- `BLOB_LAYOUT` till `"root"` eller `"folder"` beroende på om du ska köra Blob-trigger.
- `FLOW_URL` till din HTTP-triggeradress om du använder den vägen, annars tom.

Spara med Ctrl+O och Enter, avsluta med Ctrl+X.

### Alternativ B, kopiera upp din färdiga fil (scp)

Har du redan fyllt i rätt värden i din lokala `app.py` kan du kopiera upp den i
stället. `/opt/arendeapp` ägs av root, så lägg filen i `/tmp` först och flytta
den sedan på plats:

    scp -i <din-nyckel> app.py azureuser@<publik-ip>:/tmp/app.py

Logga sedan in på VM:en och flytta filen dit den ska:

    sudo mv /tmp/app.py /opt/arendeapp/app.py

Kör du via Bastion i stället för direkt SSH, använd `az network bastion tunnel`
för att öppna en lokal port mot VM:en och kör `scp` mot den porten.

### Starta om och verifiera (båda alternativen)

Starta om backenden så att den läser den nya koden:

    sudo systemctl restart arendeapp

Kontrollera att den kom upp och läser rätt värden:

    curl http://localhost:5000/health

Hälsokollen svarar nu med `blob_layout` och `flow_configured`, så du ser direkt
att layouten stämmer och om en flödesadress är inlagd. Gamla ärenden i lagringen
påverkas inte, ändringen gäller nya ärenden som skickas in efter omstarten.

## Testa

Öppna webbserverns publika IP i webbläsaren, fyll i formuläret och skicka. Du ska
mötas av en tack-sida med ett ärende-id. Verifiera sedan att ärendet faktiskt
hamnade i lagringen:

    az storage blob list \
      --account-name <ditt konto> \
      --container-name arenden \
      --auth-mode login \
      --output table

Med standardläget `root` ligger ärendet som `arende-<id>.json` direkt i roten. Har
du valt `folder` ligger det som `<id>/arende.json` i stället.

Backenden har också en enkel hälsokoll:

    curl http://localhost:5000/health

## G och VG

Grunden här räcker för G-kärnan: ett ärende skrivs till Blob via den hanterade
identiteten, utan nyckel. VG-utmaningarna kopplar vidare till resten av v37:
stäng publik åtkomst och nå kontot via privat endpoint i snet-db, lyft ut
kontonamnet till en miljövariabel i stället för hårdkodat, eller servera en ren
informationssida statiskt från `$web` vid sidan om (men just formuläret måste
ligga kvar på servern, eftersom det skriver via identiteten).

## En not om säkerhet

Backenden kör Flasks inbyggda utvecklingsserver, vilket räcker gott för labben.
I skarp drift skulle man sätta gunicorn framför och köra sidan över HTTPS. Håll
publik åtkomst till lagringen stängd, det är hela poängen med att gå via
identiteten i stället för nyckel. `FLOW_URL` innehåller en hemlig signatur, så i
skarp drift hör den hemma i en miljövariabel, inte hårdkodad i källan.
