# 🚀 1-Click AWS Deployment Guide (For Non-Coders)

Want to run your own instance of the **Sinhala ↔ Tamil Real-Time Voice Translator Backend** but don't know how to code or use the terminal? No problem!

Follow these simple steps to deploy the backend on AWS using an automated "User Data" script. The server will build and configure itself automatically!

---

## Step 1: Launch an AWS EC2 Instance
1. Log into your [AWS Management Console](https://console.aws.amazon.com/).
2. Go to the **EC2 Dashboard** and click the orange **Launch instance** button.
3. **Name:** Give your server a name (e.g., `Translator-Backend`).
4. **OS Images:** Select **Ubuntu** (Ubuntu Server 24.04 LTS is recommended).
5. **Instance Type:** Select **t2.micro** or **t3.micro** (Free-tier eligible).
6. **Key Pair:** Select an existing key pair or click "Create new key pair" (you won't need to use this unless you want to SSH later, but AWS requires it).

## Step 2: Configure Network & Security (Important!)
In the **Network settings** section, make sure you check the following boxes so the world can access your API:
- ✅ Allow SSH traffic from anywhere (Port 22)
- ✅ Allow HTTP traffic from the internet (Port 80)
- ✅ Allow HTTPS traffic from the internet (Port 443)

**Wait, you also need Port 8000!** 
Click the **Edit** button in the Network settings, click **Add security group rule**, and set:
- **Type:** Custom TCP
- **Port range:** `8000`
- **Source type:** Anywhere (`0.0.0.0/0`)

## Step 3: Paste the Magic Auto-Deploy Script
Scroll all the way down to the bottom of the page and click the **Advanced details** dropdown. 

Scroll to the very bottom of that section until you see a large text box labeled **User data**. Copy the script below and paste it directly into that box:

```bash
#!/bin/bash
# 1. Add Swap Memory (Required for Free Tier servers with 1GB RAM)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab

# 2. Install Docker & Git
apt-get update
apt-get install ca-certificates curl git -y
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y

# 3. Clone the Project & Setup
git clone https://github.com/UVSHUB/Tamil-and-Sinhala-Converter.git /home/ubuntu/Tamil-and-Sinhala-Converter
cd /home/ubuntu/Tamil-and-Sinhala-Converter

# Configure Environment Variables (.env)
cat << 'EOF' > .env
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
TRANSLATE_MODEL=gemini-3.1-flash-lite-preview
TTS_MODEL=gemini-3.8-flash-tts
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
ALLOWED_ORIGINS=*
EOF

# 4. Start all services (Backend, Frontend, and Nginx reverse proxy)
docker compose up -d --build
```

> [!NOTE]
> Replace `YOUR_GEMINI_API_KEY_HERE` with your actual Google Gemini API Key before running or edit `/home/ubuntu/Tamil-and-Sinhala-Converter/.env`.

---

## Step 4: Important — Browser Microphone Permission (HTTPS Requirement)

Modern web browsers (Google Chrome, Microsoft Edge, Safari, Firefox) **strictly block microphone access (`getUserMedia`) on remote IP addresses unless HTTPS is enabled**.

To use the voice translation interface on AWS:

### Option A: Use a Free Domain with SSL (Recommended)
1. Point any free domain (or Cloudflare DNS) to your EC2 Public IP.
2. In Cloudflare, enable the orange cloud (Proxy) — you get automatic, instant **free HTTPS/SSL** with zero server setup!
3. Open `https://your-domain.com`.

### Option B: Local Browser Testing Without a Domain
If accessing directly via `http://<EC2-PUBLIC-IP>:8000`:
1. In Chrome/Edge, visit: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
2. Add your EC2 URL: `http://<YOUR_EC2_PUBLIC_IP>:8000`
3. Set the flag to **Enabled** and restart the browser. This allows your browser to use the microphone on your EC2 instance.

---

## Step 5: How to Connect to Your Backend

Once your container is running:
- **Web App**: Open `http://YOUR_EC2_PUBLIC_IP:8000` (or `http://YOUR_EC2_PUBLIC_IP` through Nginx)
- **Health Check**: `http://YOUR_EC2_PUBLIC_IP:8000/api/v1/health`
- **WebSocket URL**: `ws://YOUR_EC2_PUBLIC_IP:8000/ws/translate-auto?target=Tamil`

