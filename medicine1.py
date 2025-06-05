import streamlit as st
import datetime
import re
from PIL import Image
import base64
import io
import os
import requests
from groq import Groq
from pyzbar.pyzbar import decode
import fitz  # PyMuPDF

client = Groq(api_key="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")

st.set_page_config(page_title="Medicine Expiry Scanner", layout="centered")
st.title("🧪 Medicine Expiry Scanner (GROQ AI)")

# Language selection for multilingual prompt
lang = st.selectbox("Select Language for Extraction", ["English", "Hindi", "Spanish", "French", "German"])
prompt_text = f"Extract clearly the medicine name, expiry date, batch number, and manufacturer in {lang} from this image. Provide only the key-value pairs in your response."

# Camera input or file uploader
option = st.radio("Choose Input Method:", ["Upload Image", "Use Camera"])

if option == "Upload Image":
    uploaded_file = st.file_uploader("Upload a photo of the medicine box", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image = Image.open(uploaded_file)
elif option == "Use Camera":
    captured_image = st.camera_input("Capture Medicine Box")
    if captured_image:
        image = Image.open(captured_image)
else:
    image = None

if 'image' in locals() and image:
    st.image(image, caption="Input Image", use_column_width=True)

    with st.spinner("Extracting details using GROQ Vision model..."):
        # QR/Barcode decoding
        decoded = decode(image)
        barcode_data = decoded[0].data.decode("utf-8") if decoded else None

        # Convert image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        image_data_uri = f"data:image/png;base64,{img_str}"

        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": image_data_uri}}
                    ]
                }
            ],
            temperature=0.3,
            max_completion_tokens=1024,
            top_p=1,
            stream=False,
            stop=None,
        )

        result_text = completion.choices[0].message.content if completion.choices else ""

        # Extract fields with improved matching
        def extract_field(key, text):
            pattern = rf"(?i){key}[^:\n]*[:\-\s]+([A-Za-z0-9\s,./()-]+)"
            match = re.search(pattern, text)
            return match.group(1).strip() if match else "Not Found"

        med_name = extract_field("name", result_text)
        expiry = extract_field("exp", result_text)
        batch = extract_field("batch", result_text)
        mfg = extract_field("manufacturer", result_text)

        # Parse expiry date
        def parse_expiry(exp_str):
            try:
                exp_str = exp_str.replace(" ", "")
                for fmt in ("%Y-%m", "%m/%Y", "%m-%Y", "%b-%Y", "%B-%Y"):
                    try:
                        return datetime.datetime.strptime(exp_str, fmt).date()
                    except:
                        continue
                return None
            except:
                return None

        expiry_date = parse_expiry(expiry)
        today = datetime.date.today()
        expired = expiry_date < today if expiry_date else None

        # Barcode lookup via OpenFDA
        barcode_lookup_data = "Not Found"
        if barcode_data:
            try:
                response = requests.get(f"https://api.fda.gov/drug/ndc.json?search=product_ndc:{barcode_data}")
                if response.status_code == 200:
                    results = response.json().get("results", [])
                    if results:
                        med_info = results[0]
                        brand = med_info.get("brand_name", "Unknown")
                        labeler = med_info.get("labeler_name", "Unknown")
                        barcode_lookup_data = f"{brand}, {labeler}"
            except Exception as e:
                barcode_lookup_data = f"Error fetching data: {e}"

        # Display
        st.subheader("📋 Extracted Details")
        st.markdown(f"""
        | Field           | Value                                                  |
        |-----------------|--------------------------------------------------------|
        | **Name**        | {med_name}                                            |
        | **Expiry**      | {expiry} {'❌ Expired' if expired else '✅ Valid' if expiry_date else ''} |
        | **Batch No.**   | {batch}                                               |
        | **Manufacturer**| {mfg}                                                 |
        | **Barcode/QR**  | {barcode_data or 'Not Detected'}                      |
        | **Lookup Info** | {barcode_lookup_data}                                 |
        """)

        # Export to CSV
        if st.button("Export as CSV"):
            csv_data = f"Field,Value\nName,{med_name}\nExpiry,{expiry}\nBatch No.,{batch}\nManufacturer,{mfg}\nBarcode/QR,{barcode_data or 'Not Detected'}\nLookup Info,{barcode_lookup_data}\n"
            st.download_button("Download CSV", data=csv_data, file_name="medicine_info.csv", mime="text/csv")

        # Export to PDF
        if st.button("Export as PDF"):
            pdf_path = "/tmp/medicine_info.pdf"
            pdf = fitz.open()
            page = pdf.new_page()
            page.insert_text((50, 100), f"Medicine Name: {med_name}")
            page.insert_text((50, 120), f"Expiry Date: {expiry} {'❌ Expired' if expired else '✅ Valid' if expiry_date else ''}")
            page.insert_text((50, 140), f"Batch No.: {batch}")
            page.insert_text((50, 160), f"Manufacturer: {mfg}")
            page.insert_text((50, 180), f"Barcode/QR: {barcode_data or 'Not Detected'}")
            page.insert_text((50, 200), f"Lookup Info: {barcode_lookup_data}")
            pdf.save(pdf_path)
            with open(pdf_path, "rb") as f:
                st.download_button("Download PDF", f, file_name="medicine_info.pdf", mime="application/pdf")
else:
    st.info("Upload or capture a clear image of a medicine box label with visible text.")
