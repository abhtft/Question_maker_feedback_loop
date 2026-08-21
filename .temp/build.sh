#!/bin/bash

#automate for unix like system


echo "Starting build process..."

python -m venv venv

#for linux
source venv310/bin/activate

#2. for windows
venv\Scripts\activate

python emailmessage.py

venv\Scripts\deactivate

# Upgrade pip and install Python dependencies
python -m ensurepip --upgrade
pip install --upgrade pip
pip install -r requirements.txt && npm run build && python app.py #always use user word
python check_requirements.py


npm run build && python app.py

#first should check backend testing

source venv/bin/activate

rm -rf Question_maker Question_maker_langchain1
npm install
npm run build


if [ ! -d "dist" ]; then
    echo "Error: dist directory not found after build"
    exit 1
fi

if [ ! -f "dist/index.html" ]; then
    echo "Error: index.html not found in dist directory"
    exit 1
fi

echo "Build completed successfully!" 
# Run the server
python server.py

git pull origin main

namacheap _apssword: $Z%6.FWRYTY:m2

git pull https://github.com/abhtft/Question_maker_langchain1.git

#downloading pm2
curl -sL https://deb.nodesource.com/setup_16.x | sudo -E bash -
sudo apt install nodejs -y
sudo npm install -g pm2


cd /home/ubuntu/Question_maker_langchain1

pm2 start app.py --name "prashnotri" --interpreter python3
#dist issue solved


cd /home/ubuntu/Question_maker
source venv/bin/activate

pip install -r requirements.txt

 Frontend Build(local)
  npm install
  npm run build

#nginx install
  sudo ln -s /etc/nginx/sites-available/prashnotri.com /etc/nginx/sites-enabled/
  sudo nginx -t
  sudo systemctl restart nginx


  

  
#creation of ssl certificate
sudo certbot --nginx -d prashnotri.com -d www.prashnotri.com

source venv/bin/activate


cd /home/ubuntu/Question_maker

cat requirements.txt


git pull https://github.com/abhtft/Question_maker_.git
pm2 delete prashnotri  # Remove the old process if running
pm2 stop prashnotri

pip install --upgrade pip
pip install -r requirements.txt

pm2 start app.py --name "prashnotri" --interpreter /home/ubuntu/Question_maker_langchain1/venv/bin/python
pm2 status
pm2 logs prashnotri
pm2 restart prashnotri


pm2 save
pm2 startup


--------------------------

cd Question_maker_langchain1 && \
 && \
pm2 delete prashnotri || true && \
pm2 stop prashnotri || true && \
/home/ubuntu/Question_maker_langchain1/venv/bin/pip install -r requirements.txt && \
pm2 start app.py --name "prashnotri" --interpreter /home/ubuntu/Question_maker_langchain1/venv/bin/python && \
pm2 status && \
pm2 logs prashnotri


git clone https://github.com/abhtft/Question_maker_langchain1.git


---------------------------
#following occupy some space in ubuntu (but one should know its usage,less usefull)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
sudo sysctl vm.swappiness=10
sudo sysctl vm.vfs_cache_pressure=50

---------------
git fetch origin #Update your local representation of the remote repository
git diff --name-only HEAD origin/main
git checkout origin/main -- requirements.txt #finally updates local

git pull
#Purpose: Fetches and integrates changes from a remote repository
#Usage: git pull [remote] [branch]
#Effect: Combines git fetch and git merge in one command
git pull https://github.com/abhtft/Question_maker_langchain1.git


git status
git add . # Stages changes for the next commit(boggie)
git commit -m "commit message"[] #Records changes to the repository(engine)
git push origin main #Uploads local repository content to a remote repository(travel)
--------------
pip install torch==2.4.1(only under venv)


#cleaning files
#(ubuntu commands)
--------------------------
# Clean package manager cache
sudo apt-get clean
sudo apt-get autoremove

# Clean old logs
sudo rm -rf /var/log/*.gz
sudo rm -rf /var/log/*.old

# Clean temporary files
sudo rm -rf /tmp/*
sudo rm -rf /var/tmp/*

# Clean old git objects
cd /home/ubuntu/Question_maker_langchain1
git gc --prune=now

# Remove any old virtual environments
rm -rf venv
-----------------------------

ds -h
sudo growpart /dev/xvda 1
sudo resize2fs /dev/xvda1

#installing sepcific python version
sudo apt-get update
sudo apt-get install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.8 python3.8-venv python3.8-dev
python3.8 -m venv venv
source venv/bin/activate
---------------------

python3.8 --version
python3.8 -m venv venv
#windows
venv\Scripts\activate
source venv/bin/activate

python -m pip install --upgrade pip
--------------
	2. Specify Versions: Use version specifiers to prevent unexpected updates:
# In requirements.txt
package==1.2.3    # Exact version
package>=1.2.3    # Minimum version
package~=1.2      # Compatible version (1.2.x)
-------------------

Split Requirements: Separate dev and production dependencies:
requirements.txt          # Core requirements
requirements-dev.txt      # Development tools
----------------

sudo apt install -y pkg-config libcairo2-dev


nano .env---
ctrlx -y enter


----
#installing pm2
sudo apt update
sudo apt install -y nodejs npm
sudo npm install pm2 -g

(venv) ubuntu@ip-172-31-6-2:~/Question_maker_langchain1$ nslookup www.prashnotri.com
Server:         127.0.0.53
Address:        127.0.0.53#53
#says https is not yet done
Non-authoritative answer:
Name:   www.prashnotri.com
Address: 13.203.101.41




(venv) ubuntu@ip-172-31-6-2:~/Question_maker_langchain1$ curl -I http://127.0.0.1:5000/
HTTP/1.1 404 NOT FOUND
Server: Werkzeug/3.0.6 Python/3.8.20
Date: Mon, 12 May 2025 16:53:09 GMT
Content-Type: application/json
Content-Length: 36
Access-Control-Allow-Origin: *
Connection: close

/--------It mwans app is running but not some proper



flask is running------------

-------------

sudo apt update
sudo apt install certbot -y
sudo apt install python3-certbot-nginx -y
sudo certbot --nginx -d prashnotri.com -d www.prashnotri.com
sudo certbot renew --dry-run
sudo systemctl restart nginx


ssh -i "abhi.pem" ubuntu@ec2-13-203-101-41.ap-south-1.compute.amazonaws.com

-----------
python code_sample.py


docker-compose up --build

echo "# Question_maker_feedback_loop" >> README.md
git init
#git add README.md
git commit -m "first commit"
git branch -M main
git remote -v
git remote add origin https://github.com/abhtft/Question_maker_feedback_loop.git
git push -u origin main