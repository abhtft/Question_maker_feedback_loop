#can i run on free tier VM and also azure web app for usage under 200$.Mu undertanding is web app will cut from free credit but vm 750 hours are free

#can i upload template to my deployed n8n

#free tier east us is best


sudo apt update && sudo apt upgrade -y

#step1:install dependencies
sudo apt install pkg-config libcairo2-dev libgirepository1.0-dev -y

#step2:install python3.10
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.10 python3.10-venv python3.10-dev -y



#creating environment files
create .env file
nano .env

ctrl+x to save and exit

#step3:install git

sudo apt install git -y

#always same python version

#docker install

#removing file in ubuntu
rm -rf Question_Maker_V4

#step4:clone the repository
#should only be in main not in cd one
git clone https://github.com/abhtft/Question_Maker_V4.git
cd Question_Maker_V4
(betterway as very quick way and only once need install)

#to call just changed this file
cd ~/Question_Maker_V4
git pull origin main

#venv is good way to install dependencies
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate




#step6:install dependencies
pip install -r requirements.txt

#step7:run the application
python3.10 app.py

#step5:install pm2
sudo apt install npm -y
sudo npm install -g pm2

#step6:run the application completely wrong setup you gave
#pm2 start gunicorn --name question-maker --interpreter python3.10 -- \-w 4 -b 0.0.0.0:5000 app:app
pm2 start app.py --name question-maker --interpreter python3.10
#pm2 was not proeprly deployed so gave error


pm2 status:  checking the status of the application
pm2 logs question-maker:  checking the logs of the application
pm2 stop question-maker:  stopping the application
pm2 delete question-maker:  deleting the application
pm2 restart question-maker
pm2 save:  saving the application
pm2 unstartup:  unstartup the application

pm2 status
 pm2 logs question-maker



# Run the container
curl http://127.0.0.1:5000

#local and public ipv4 verification done.

#after app running local then only nginx make sense

#nginx is a web server that can be used to serve the application
#nginx is a load balancer that can be used to serve the application
#nginx is a reverse proxy that can be used to serve the application
#nginx is a web server that can be used to serve the application
#nginx is a web server that can be used to serve the application



#---------------------------------------------------

#installing via docker

#step1:install nginx (connecting local ipv4 with custom domain)but in http not https

sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled

sudo nano /etc/nginx/sites-available/prashnotri


server {
    listen 80;
    server_name www.prashnotri.com;  # OR use your public IP address if no domain

    location / {
        proxy_pass http://127.0.0.1:5000;  # Flask is running on port 5000
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

sudo apt update
sudo apt install nginx -y



After installation, verify it's running:
sudo systemctl status nginx
If it's not running, start it:
sudo systemctl start nginx

sudo systemctl restart nginx

#what are its uses?
#it is used to get a free ssl certificate
#it is used to secure the connection between the user and the server
#it is used to encrypt the data between the user and the server
#it is used to secure the connection between the user and the server


#after nginx we need lets encrpt

sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx

#check the final website

#now we need to deploy the application on azure web app

cd #.. towards back
