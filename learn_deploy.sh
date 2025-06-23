#docker on ec2

#step
sudo yum update -y
sudo yum install docker -y
sudo service docker start
sudo usermod -a -G docker ec2-user

#2. install docker compose
sudo curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

#3. restart docker
sudo systemctl restart docker
newgrp docker

docker ps
#4. pull the image
#3. pull the image(image is not running and container is running)
docker pull abhishek838/paper_generator:latest

#4. run the container
docker run -d -p 80:5000 --name myapp abhishek838/paper_generator:latest

#5. check the container
docker ps

#6. stop the container

ubuntu@ip-172-31-6-26:~$ docker ps
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
ubuntu@ip-172-31-6-26:~$ docker run -d -p 80:5000 --name myapp abhishek838/paper_generator:latest
c511a9576f76e5d0caa7f4a57a91fdae0ab0ae510553c0a5bb710ace5f34ad15
ubuntu@ip-172-31-6-26:~$ docker ps
CONTAINER ID   IMAGE                                COMMAND                  CREATED         STATUS                            PORTS                                     NAMES
c511a9576f76   abhishek838/paper_generator:latest   "gunicorn --bind 0.0…"   9 seconds ago   Up 8 seconds (health: starting)   0.0.0.0:80->5000/tcp, [::]:80->5000/tcp   myapp
ubuntu@ip-172-31-6-26:~$

nano docker-compose.yml

#

curl http://127.0.0.1:5000



docker docker-compose up -d



----------------------------------
docker run -d -p 5000:5000 --name paper-generator --env-file .env abhishek838/paper_generator:latest