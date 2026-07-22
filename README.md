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
- cluster k3s attivo (es. Rancher Desktop in modalità **containerd**)
- `kubectl` configurato per il cluster
- `nerdctl` disponibile per costruire le immagini

> **Nota sull'engine.** Con Rancher Desktop in modalità containerd, `nerdctl` e
> k3s condividono lo stesso containerd. Le immagini vengono costruite
> direttamente nel namespace containerd `k8s.io`, quindi il cluster le vede
> subito **senza bisogno di un registry**. I deployment referenziano le immagini
> locali (es. `lib-prestito:1.0`) con `imagePullPolicy: IfNotPresent`.
> Il vecchio approccio con registry interno (`registry.default.svc.cluster.local:5000`)
> non funzionava perché il containerd del nodo risolve i nomi tramite il resolver
> dell'host e non tramite CoreDNS, quindi non riusciva a risolvere un nome DNS
> interno al cluster.

### Costruire le immagini nel cluster
```bash
# costruisce lib-prestito, lib-modifica, lib-worker, lib-frontend
# nel namespace containerd k8s.io usato da k3s
./k8s/push-images.sh
```

In alternativa, una singola immagine:
```bash
nerdctl --namespace k8s.io build -t lib-prestito:1.0 ./prestito
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

### Accesso a RabbitMQ in k3s
Il service `rabbitmq` è di tipo `ClusterIP` (non esposto da ingress), quindi
per raggiungerlo dall'host serve un `port-forward`:

```powershell
# management UI (http://localhost:15672)
kubectl port-forward svc/rabbitmq 15672:15672

# broker AMQP (per client esterni su localhost:5672)
kubectl port-forward svc/rabbitmq 5672:5672
```

- Management UI: http://localhost:15672
- Credenziali: utente `libreria`, password `libreria` (dal secret `app-secrets`)

Il `port-forward` resta attivo finché il comando è in esecuzione: tienilo aperto
in un terminale dedicato. All'interno del cluster i servizi usano invece
l'hostname `rabbitmq` sulla porta `5672`, senza bisogno di port-forward.

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
