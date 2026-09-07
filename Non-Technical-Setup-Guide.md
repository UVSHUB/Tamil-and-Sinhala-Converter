# 🚀 SinTam Voice Translator: Quick Start Guide

Welcome! This guide will help you get the Real-Time Trilingual Voice Translator running on your computer in just a few minutes. You don't need any coding knowledge to do this!

## 📝 Step 1: Install Required Software
Your computer needs two standard programs installed to run this application:
1. **Download Python:** [Click here to download Python](https://www.python.org/downloads/). When installing, **make sure to check the box that says "Add Python to PATH"** at the very bottom of the installer window.
2. **Download Node.js:** [Click here to download Node.js](https://nodejs.org/). The standard "LTS" (Long Term Support) version is perfect. Just click Next through the default installation.

## 🔑 Step 2: Add Your Secret Key
The translator uses Google's AI to work. You need to provide your unique AI "Key".
1. Open the project folder (`Tamil-and-Sinhala-Converter`).
2. Find the file named **`.env.example`**.
3. Right-click the file and select **Rename**. Change the name to exactly **`.env`** (Make sure there is a dot at the beginning and no ".example" at the end).
4. Open this `.env` file using Notepad (or any text editor).
5. Find the line that says `GEMINI_API_KEY=AIzaSyYourActualGeminiApiKeyHere`.
6. Replace `AIzaSyYourActualGeminiApiKeyHere` with your actual Google Gemini API key. Save and close the file.

## ▶️ Step 3: Start the Application!
We have created a magical shortcut file for you!

1. In the main project folder, find the file named **`start_app.bat`**.
2. **Double-click `start_app.bat`**.

That's it! 
* A black terminal window will open and automatically download all the required files. (This might take a minute or two the very first time you run it).
* Once it finishes, it will open two minimized windows in the background (these are the server brains running).
* Finally, it will tell you it's ready. Open your web browser (like Chrome or Edge) and go to: **[http://localhost:5173](http://localhost:5173)**

*Note: When you are done using the translator for the day, just find those two black windows running in your taskbar and close them to turn off the server.*
