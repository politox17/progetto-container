# Microservizi Libreria

Questa applicazione è un esempio concreto di architettura a microservizi per la gestione di prestiti di libri. Include:
- due API FastAPI (`prestito` e `modifica`)
- RabbitMQ per la sincronizzazione asincrona
- due database PostgreSQL separati
- un worker Node.js per consumare notifiche
- un frontend statico servito con Nginx

Il progetto può essere eseguito sia con Docker Compose sia su un cluster k3s.

## Architettura

```text
Browser --> frontend --> prestito API --> PostgreSQL prestito
                 |                           |
                 |                           | RabbitMQ (prestito.creato)
                 |                           v
                 |                        modifica API --> PostgreSQL modifica
                 |
                 +--> worker (consuma notifiche da RabbitMQ)
```

## Flussi principali

- `POST /prestiti` sul servizio `prestito`:
  - salva il prestito nel DB `prestito`
  - pubblica l’evento `prestito.creato` su RabbitMQ
  - pubblica una notifica sulla coda `notifiche`
- `modifica` consuma `prestito.creato` e aggiorna il proprio DB
- `PATCH /prestiti/{id}` sul servizio `modifica`:
  - aggiorna la scadenza nel DB `modifica`
  - pubblica `prestito.modificato`
- `prestito` riceve `prestito.modificato` e sincronizza il proprio DB
- `worker` consuma le notifiche dalla coda `notifiche`

## 1. Avvio con Docker Compose

### Prerequisiti
- Docker Desktop o Docker Engine
- Docker Compose

### Comando
```powershell
docker compose up -d --build
```

### Accesso locale
- Frontend: http://localhost:8080
- Prestito API: http://localhost:8000/docs
- Modifica API: http://localhost:8001/docs
- RabbitMQ UI: http://localhost:15672
- Portainer: https://localhost:9443

### Verifica rapida
```powershell
docker compose logs -f prestito modifica worker
```

### Controllo dei database
```powershell
docker exec -it lib-postgres-prestito psql -U libreria -d libreria -c "SELECT id, utente, libro, scadenza FROM prestiti ORDER BY id DESC;"
docker exec -it lib-postgres-modifica psql -U libreria -d libreria_modifica -c "SELECT id, utente, libro, scadenza FROM prestiti_modificabili ORDER BY id DESC;"
```

### Teardown
```powershell
docker compose down
docker compose down -v
```

## 2. Avvio su k3s

### Prerequisiti
- cluster k3s attivo
- `kubectl` configurato per il cluster
- Docker disponibile per costruire le immagini

### Costruire e pubblicare le immagini
```powershell
# 1) avvia il registry interno al cluster
kubectl apply -f k8s/registry-deployment.yml

# 2) porta il registry locale verso l'host
kubectl port-forward svc/registry 5000:5000

# 3) costruisci e push delle immagini verso il registry
./k8s/push-images.sh
```



### Applicare i manifest
```powershell
kubectl apply -f k8s
```

### Verificare il deploy
```powershell
kubectl get pods,svc,ingress
kubectl describe pod <nome-pod>
kubectl logs <nome-pod>
```



### Accesso in k3s
Dopo che i pod sono Running:
- Frontend: http://localhost/
- Prestito API: http://localhost/api/prestito/docs
- Modifica API: http://localhost/api/modifica/docs

## 3. Debugging su Kubernetes

### Controllare lo stato dei pod
```powershell
kubectl get pods -A
kubectl get pods
kubectl describe pod <nome-pod>
```

### Leggere i log
```powershell
kubectl logs deploy/prestito
kubectl logs deploy/modifica
kubectl logs deploy/worker
kubectl logs <nome-pod>
```

### Controllare service e ingress
```powershell
kubectl get svc
kubectl get ingress
kubectl describe ingress frontend
kubectl describe ingress prestito
kubectl describe ingress modifica
```

### Entrare in un container
```powershell
kubectl exec -it <nome-pod> -- sh
```

## 4. Pulizia

### Docker Compose
```powershell
docker compose down
docker compose down -v
```

### k3s
```powershell
kubectl delete -f k8s
```
