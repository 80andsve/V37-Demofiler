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

I `app.py`, längst upp, finns ett tydligt markerat block:

    STORAGE_ACCOUNT = "stnovatrixXXXX"
    CONTAINER = "arenden"

Byt `STORAGE_ACCOUNT` mot ditt eget globalt unika kontonamn (samma konto som
provisioneringen skapade). Behåll `CONTAINER` som `arenden` om du inte döpt om
den. Inget annat behöver röras för att grunden ska fungera.

Ändrar man i `app.py` måste ändringen även in i `cloud-init.txt` (samma kod
ligger inbäddad där), eftersom det är `cloud-init.txt` som faktiskt driftsätts.

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

Har du redan en körande VM räcker det att lägga in samma innehåll och köra om
`cloud-init`, men enklast för er är att skapa VM:en med rätt custom-data
från början.

## Testa

Öppna webbserverns publika IP i webbläsaren, fyll i formuläret och skicka. Du ska
mötas av en tack-sida med ett ärende-id. Verifiera sedan att ärendet faktiskt
hamnade i lagringen:

    az storage blob list \
      --account-name <ditt konto> \
      --container-name arenden \
      --auth-mode login \
      --output table

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
identiteten i stället för nyckel.
