# Lägga till V37-formuläret på en VM som redan finns

Har du en VM som skapades före V37 saknar den formuläret, eftersom `cloud-init` bara körs när en VM skapas. Du behöver inte skapa om VM:en. Vi gör det i två delar: först Azure-sidan (helt oförstörande), sedan lägger vi formuläret på VM:en för hand.

> **Har din VM redan formuläret men pekar på fel lagringskonto?** Då behöver du inte göra allt nedan. Hoppa direkt till avsnittet "Sätt ditt kontonamn i appen" i Del 2, ändra `STORAGE_ACCOUNT` och starta om tjänsten. Är du osäker, kör `systemctl status arendeapp`. Svarar den `could not be found` saknas appen, och då gäller hela guiden.

## Del 1: Azure-sidan med storage.sh

Scriptet skapar lagringskontot och containern, ger din befintliga VM en hanterad identitet och sätter rollen på containern. Inget rivs.

1. Öppna `storage.sh` och sätt `APP_NAME` till din webb-VM:s namn, till exempel `vm-novatrix-web`. `APP_KIND` är redan `vm`.
2. Kör i Azure Cloud Shell (bash):

   ```
   bash storage.sh
   ```

3. Skriv upp kontonamnet scriptet skriver ut (`stnovatrixNNNN`), det behövs strax.

## Del 2: Formuläret på VM:en

Cloud-init körs bara när en VM skapas, så på en befintlig VM gör du samma sak för hand.

Kopiera först upp de fyra filerna från mappen där du packat upp V37. Kör detta på din egen dator:

```
scp -i novatrix_key app.py index.html nginx-arende.conf arendeapp.service azureuser@<din-vm-ip>:~
```

SSH:a sedan in och lägg filerna där cloud-init hade lagt dem:

```
ssh -i novatrix_key azureuser@<din-vm-ip>
sudo apt update && sudo apt install -y nginx python3 python3-pip
sudo pip3 install flask azure-identity azure-storage-blob
sudo mkdir -p /opt/arendeapp
sudo cp ~/app.py /opt/arendeapp/app.py
sudo cp ~/index.html /var/www/html/index.html
sudo cp ~/nginx-arende.conf /etc/nginx/sites-available/default
sudo cp ~/arendeapp.service /etc/systemd/system/arendeapp.service
```

Klagar `pip3` på systemet, lägg till `--break-system-packages` sist på pip-raden.

Sätt ditt kontonamn i appen, samma som `storage.sh` skrev ut:

```
sudo nano /opt/arendeapp/app.py
```

Ändra raden `STORAGE_ACCOUNT = "stnovatrixNNN"` till ditt kontonamn och spara (Ctrl+O, Enter, Ctrl+X).

Starta igång allt:

```
sudo systemctl daemon-reload
sudo systemctl enable --now arendeapp
sudo systemctl restart nginx
```

## Kontrollera

```
systemctl status arendeapp
curl localhost:5000/health
```

Tjänsten ska vara active (running), och `/health` ska visa ditt kontonamn.

Öppna sedan VM:ens publika IP i webbläsaren, skicka in ett testärende och lista containern:

```
az storage blob list --account-name <ditt konto> --container-name arenden --auth-mode login -o table
```

Rolltilldelningen kan ta en minut eller två att slå igenom. Får du 403 direkt efter `storage.sh`, vänta lite och testa igen.

## Att ta med sig

Allt du gör för hand i Del 2 är exakt det `cloud-init.txt` gör åt dig när en VM skapas. Nästa gång du bygger en webb-VM räcker det att skapa den med `--custom-data cloud-init.txt`, så sköts hela formuläret automatiskt.
