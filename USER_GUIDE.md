# Developer User Guide: Sinhala & Tamil Converter

Welcome! This guide explains how to install, setup, and use the **Sinhala & Tamil Converter** in your own projects. It is written in simple, plain language so any developer can get started in just a few minutes.

---

## 1. What is this Project?

This project lets you translate text easily between **Sinhala** and **Tamil** in three ways:

1. **Python Library (`sinhala-tamil-converter`)**: Add translation functions directly inside your own Python code with 2-3 lines of code.
2. **Terminal / Command Line Tool (`st-convert`)**: Translate sentences directly from your terminal window.
3. **Web Application (Optional)**: A full web interface and API server for real-time text and voice translation.

---

## 2. Before You Start (Prerequisites)

Make sure you have the following ready:
* **Python**: Version 3.9 or higher installed on your computer.
* **Google Gemini API Key**: A free or paid key from [Google AI Studio](https://aistudio.google.com/).

---

## 3. Step-by-Step Setup

### Step 1: Install the Package

Open your Terminal (macOS/Linux) or Command Prompt / PowerShell (Windows) and run:

```bash
pip install git+https://github.com/UVSHUB/Tamil-and-Sinhala-Converter.git
```

*(If you have downloaded the code locally to your computer, open a terminal in that folder and run `pip install -e .` instead.)*

---

### Step 2: Set Up Your API Key

The converter uses Google Gemini to translate text accurately. The easiest and safest way is to save your API key as an environment variable.

* **Windows (Command Prompt):**
  ```cmd
  set GEMINI_API_KEY="YOUR_ACTUAL_API_KEY_HERE"
  ```

* **Windows (PowerShell):**
  ```powershell
  $env:GEMINI_API_KEY="YOUR_ACTUAL_API_KEY_HERE"
  ```

* **macOS / Linux:**
  ```bash
  export GEMINI_API_KEY="YOUR_ACTUAL_API_KEY_HERE"
  ```

> 💡 **Tip:** Replace `"YOUR_ACTUAL_API_KEY_HERE"` with your real key from Google AI Studio.

---

## 4. How to Use the Converter in Python

Create a new Python file (for example `test_translator.py`) and try any of the simple examples below.

### Example A: Quickest Sinhala to Tamil Translation
If you set the `GEMINI_API_KEY` in Step 2, you only need 3 lines of code:

```python
from sinhala_tamil_converter import translate_sinhala_to_tamil

# Sinhala input text: "Ayubowan, obata kohomada?"
sinhala_text = "ආයුබෝවන්, ඔබට කොහොමද?"

# Translate Sinhala text to Tamil
result = translate_sinhala_to_tamil(sinhala_text)
print(result)
# Expected Output (Tamil): வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?
```

---

### Example B: Tamil to Sinhala Translation

```python
from sinhala_tamil_converter import translate_tamil_to_sinhala

# Tamil input text: "Vanakkam, ningal eppati irukkirirkal?"
tamil_text = "வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?"

# Translate Tamil text to Sinhala
result = translate_tamil_to_sinhala(tamil_text)
print(result)
# Expected Output (Sinhala): ආයුබෝවන්, ඔබට කොහොමද?
```

---

### Example C: Automatic Language Detection
You don't even need to specify whether the input is Sinhala or Tamil! The package can detect it automatically:

```python
from sinhala_tamil_converter import auto_translate

# Input text (Sinhala): "Subha udasanak"
result = auto_translate("සුභ උදෑසනක්")

print(f"Translated Text: {result.text}")
print(f"Source Language: {result.source_language}")
print(f"Target Language: {result.target_language}")
# Expected Output: Translated Text: காலை வணக்கம் (Tamil: "Kalai vanakkam")
```

---

### Example D: Providing the API Key Directly in Code
If you prefer to pass the API key inside your script instead of using environment variables:

```python
from sinhala_tamil_converter import SinhalaTamilConverter

# Initialize converter with API key
converter = SinhalaTamilConverter(api_key="YOUR_ACTUAL_API_KEY_HERE")

# Translate Sinhala text ("Ayubowan") to Tamil
result = converter.translate("ආයුබෝවන්", source="sinhala", target="tamil")
print(result.text)
# Expected Output (Tamil): வணக்கம் ("Vanakkam")
```

---

## 5. Using the Command Line Tool (`st-convert`)

After installing the package, you can translate text directly from your terminal without writing any code!

```bash
# Translate Sinhala ("Ayubowan") to Tamil
st-convert "ආයුබෝවන්" --target tamil

# Translate Tamil ("Vanakkam") to Sinhala
st-convert "வணக்கம்" --target sinhala
```

---

## 6. Running the Full Web Application (Optional)

If you want to run the full web interface and server locally:

1. Copy `.env.example` to `.env` and add your API key:
   ```bash
   GEMINI_API_KEY=YOUR_ACTUAL_API_KEY_HERE
   ```
2. Run the automated backend setup:
   ```bash
   python setup_backend.py --run
   ```
3. Or run using Docker Compose (if Docker is installed):
   ```bash
   docker compose up
   ```
4. Open `http://localhost:5173` or `http://localhost` in your browser.

---

## 7. Troubleshooting Common Problems

| Problem | Cause | Simple Fix |
| :--- | :--- | :--- |
| **`pip` is not recognized** | Python is not added to your system PATH. | Try running `python -m pip install ...` instead. |
| **`ModuleNotFoundError: No module named 'sinhala_tamil_converter'`** | Python cannot find the package. | Make sure you ran `pip install git+https://...` or `pip install -e .` in the same Python environment. |
| **`API key missing` or `Invalid API key`** | The API key is missing or incorrect. | Check that `GEMINI_API_KEY` is set correctly in your terminal or script. |
| **PDF Export shows boxes `□□□□` or repeated `ආආආ` characters** | PDF exporter uses a code/monospace font that lacks Sinhala/Tamil Unicode glyphs. | 1. Use the `.md` file directly on GitHub/VS Code.<br>2. When printing to PDF, enable **"Embed Fonts"** and install a font like **Noto Sans Sinhala** & **Noto Sans Tamil**. |
| **Broken or garbled text in terminal** | Terminal encoding is not set to UTF-8. | Ensure your terminal or text editor uses **UTF-8** encoding. |

---

## 8. Summary Checklist for Developers

1. Install package: `pip install git+https://github.com/UVSHUB/Tamil-and-Sinhala-Converter.git`
2. Set key: `export GEMINI_API_KEY="your_key"` (or `set` on Windows)
3. Import in Python: `from sinhala_tamil_converter import translate_sinhala_to_tamil`
4. Run your script!
