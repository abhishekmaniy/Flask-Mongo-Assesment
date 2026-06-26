# Flask + MongoDB Kubernetes Assignment

## Prerequisites

- Python 3.8 or later
- Docker
- pip
- Minikube or another local Kubernetes environment

## Local Docker setup

Create the Docker network so Flask and MongoDB can resolve each other by
hostname inside the same network:

```bash
docker network create flask-network
```

Start MongoDB with authentication:

```bash
docker run -d \
  --name Flask-Mongo \
  --network flask-network \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=password123 \
  mongo:latest
```

Create `.env` in the project root:

```env
MONGO_HOST=Flask-Mongo
MONGO_PORT=27017
MONGO_USERNAME=admin
MONGO_PASSWORD=password123
MONGO_AUTH_SOURCE=admin
MONGODB_URI=mongodb://admin:password123@Flask-Mongo:27017/admin?authSource=admin
```

Run the Flask container in the same Docker network:

```bash
docker run -d \
  --name Flask-App \
  --network flask-network \
  -p 5000:5000 \
  --env-file .env \
  abhishekmaniyar3811/flask-app:latest
```

Verify:

```bash
docker ps
```

Open the app:

```bash
http://localhost:5000
```

API endpoint:

```bash
http://localhost:5000/data
```

View logs:

```bash
docker logs Flask-App
docker logs Flask-Mongo
```

Stop and remove containers and network:

```bash
docker stop Flask-App Flask-Mongo
docker rm Flask-App Flask-Mongo
docker network rm flask-network
```

## Project requirements

This project includes a `requirements.txt` file for local Python development.

The file contains the current supported versions used for this project:

- Flask==3.1.1
- Werkzeug==3.1.3
- pymongo==4.13.2
- python-dotenv==1.0.0

For local development without Docker, install dependencies with:

```bash
pip install -r requirements.txt
```

## Testing Scenarios

### Load generation and autoscaling

The autoscaling test used a cluster-local load generator to hit the Flask app continuously:

```bash
kubectl run -i --tty load-generator --image=busybox:1.28 --restart=Never -- \
  /bin/sh -c "while true; do wget -q -O- http://flask-service:5000/; done"
```

While the load generator was running, I watched the HPA with:

```bash
kubectl get hpa flask-app-hpa --watch
```

What I observed:

- `flask-app` started at 2 replicas.
- Once average CPU rose past the 70% target, the HPA increased replicas to 4 and then 5.
- After stopping the load generator, the deployment scaled back down over time.

### Issues encountered

- `metrics-server` can take a short warm-up before CPU usage appears in HPA metrics.
- A single load generator pod sometimes did not push CPU high enough on Minikube, so running multiple generator pods was more reliable.
- Scale-down is gradual, so replicas remained above 2 for a short stabilization period after load stopped.

### Database persistence test

I deleted the MongoDB pod with:

```bash
kubectl delete pod mongodb-0
```

Then I confirmed previously inserted data was still retrievable from `/data`, proving persistence.

Before scaling replicas:

![Before scaling](screenshots/before-scaling.png)

After scaling replicas:

![After scaling](screenshots/after-scaling.png)

## Kubernetes deployment

### Design choices

| Decision | Why | Alternative considered |
|---|---|---|
| StatefulSet for MongoDB | MongoDB needs stable identity and stable storage; StatefulSet gives each pod a predictable hostname and stable volume claim | Deployment would not provide stable pod identity and is less appropriate for a stateful database |
| Deployment for Flask | Flask is stateless and scales horizontally; Deployment is simpler and appropriate for app replicas | StatefulSet would be unnecessary overhead for a stateless web app |
| `hostPath` PersistentVolume on Minikube | Simple local persistence for `mongo` data under `/data/mongo` during development | Real cloud clusters should use a provider storage class (EBS/GCE PD/Azure Disk) for durability and node-failure resilience |
| Headless MongoDB Service (`clusterIP: None`) | Provides a stable DNS endpoint that resolves directly to the MongoDB pod IP, which is ideal for a single MongoDB instance | Normal ClusterIP would use a virtual load-balanced IP and would not preserve the pod-level identity that a StatefulSet expects |
| NodePort for Flask Service | Easy local access from the host machine in Minikube without requiring cloud LoadBalancer or Ingress setup | LoadBalancer/Ingress would require cloud provider support or extra configuration for local Minikube |
| MongoDB credentials in Kubernetes Secret | Keeps sensitive credentials out of the image and lets Kubernetes manage them securely | Baking credentials into a `.env` file inside the image is insecure and requires rebuilding the image to change credentials |

### Cookie point: testing scenarios

- Database interaction: verified POST to `/data` stores JSON in MongoDB and GET returns the stored documents.
- Autoscaling: verified HPA for `flask-app` reacts to CPU load and scales replicas between 2 and 5.
- Simulated load: used repeated requests to `/` inside the cluster and observed the HPA metrics change.
- Issues: older Flask/Werkzeug/pymongo versions from the assignment caused compatibility issues, so newer supported versions were used instead.

## Service hostnames and DNS resolution

Kubernetes uses CoreDNS as the cluster's internal DNS server. Every Service is assigned a DNS name in the form:

```
<service-name>.<namespace>.svc.cluster.local
```

Pods are configured through `/etc/resolv.conf` to query CoreDNS, which is why the short service name `mongodb-service` resolves correctly without the full suffix.

The MongoDB Service is headless (`clusterIP: None`), so DNS lookup does not return a virtual load-balanced ClusterIP. Instead, `mongodb-service` resolves directly to the MongoDB pod IP, giving the Flask pod a stable direct connection to the stateful MongoDB instance.

Build and push the Flask image:

```bash
cd flask-mongodb-k8s
docker build -t abhishekmaniyar3811/flask-app:latest .
docker login
docker push abhishekmaniyar3811/flask-app:latest
```

Start Minikube and enable metrics-server:

```bash
minikube start
minikube addons enable metrics-server
```

Apply manifests in order:

```bash
cd k8s
kubectl apply -f mongo-secret.yaml
kubectl apply -f mongo-pv-pvc.yaml
kubectl apply -f mongo-statefulset.yaml
kubectl apply -f mongo-service.yaml
kubectl apply -f flask-deployment.yaml
kubectl apply -f flask-service.yaml
kubectl apply -f flask-hpa.yaml
```

The MongoDB PV/PVC persist data from the pod's `/data/db` directory to the host path `/data/mongo`, so MongoDB data survives pod restarts or recreation.

### Replicas and Autoscaling

- Flask Deployment replicas: `2`
- HPA minimum replicas: `2`
- HPA maximum replicas: `5`
- HPA CPU utilization target: `70%`

Verify deployment:

```bash
kubectl get pods
kubectl get pvc
kubectl get svc
kubectl get hpa
```

Access Flask via NodePort:

```bash
minikube service flask-service --url
```

Local Docker hostname:

- `Flask-Mongo` is used inside the Docker network by the Flask container.

Kubernetes hostnames:

- `mongodb-service` for MongoDB
- `flask-service` for Flask

In Kubernetes, the Flask pod uses `MONGO_HOST=mongodb-service`. The cluster
DNS resolves `mongodb-service` to the MongoDB service IP, which reaches the
MongoDB pod. The service name is stable even if pod IPs change.

## Resource requests and limits

### Flask container

```yaml
resources:
  requests:
    cpu: "200m"
    memory: "250Mi"
  limits:
    cpu: "500m"
    memory: "500Mi"
```

### MongoDB container

```yaml
resources:
  requests:
    cpu: "0.2"
    memory: "250Mi"
  limits:
    cpu: "0.5"
    memory: "500Mi"
```

A request is a scheduler guarantee: Kubernetes uses it to decide where a pod can fit, and it reserves that CPU/memory for the container.

A limit is a hard ceiling: if a container uses more CPU than its limit, it is throttled; if it uses more memory than its limit, it can be OOMKilled.

Configuring both matters because requests ensure predictable placement and reserved capacity, while limits prevent any single pod from consuming so much resource that it starves other pods.

Also note that HPA CPU utilization is calculated relative to the request value, not the limit. That means the HPA target of `70%` is measured against the requested CPU, so accurate request values are critical for autoscaling behavior.

## Verify endpoints

```bash
curl http://<node-ip>:30050/

curl -X POST -H "Content-Type: application/json" \
  -d '{"sampleKey":"sampleValue"}' \
  http://<node-ip>:30050/data

curl http://<node-ip>:30050/data
```

If the deployment fails, inspect Flask logs:

```bash
kubectl logs deploy/flask-app
```

## Notes

The assignment PDF requested these package versions:

- Flask==2.0.2
- Werkzeug==2.0.3
- pymongo==3.12.0

This project uses later versions because the older versions caused compatibility issues with the current code and environment.
