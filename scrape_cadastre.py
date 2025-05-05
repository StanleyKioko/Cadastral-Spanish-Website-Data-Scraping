from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize the Chrome driver (non-headless for debugging)
options = Options()
# Comment out headless mode for debugging
# options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--window-size=1920,1080')
options.add_argument('--disable-extensions')
options.add_argument('--ignore-certificate-errors')
options.add_argument('--disable-web-security')
options.add_argument('--blink-settings=imagesEnabled=false')
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Read cadastral references from CSV
input_file = 'cadastral_references.csv'
try:
    df = pd.read_csv(input_file, header=None)
    df.columns = ['Reference']
    references = df['Reference'].tolist()
except FileNotFoundError:
    logging.error("Input file 'cadastral_references.csv' not found.")
    driver.quit()
    exit(1)

# Prepare output data
output_data = []

# Base URL
url = 'https://www1.sedecatastro.gob.es/CYCBienInmueble/OVCBusqueda.aspx?from=NuevoVisor&pest='

# Function to scrape data for a single reference with retry logic
def scrape_cadastre(reference, max_retries=3):
    for attempt in range(max_retries):
        try:
            logging.info(f"Attempt {attempt + 1} for reference {reference}")
            # Navigate to the search page
            logging.info("Loading page...")
            driver.get(url)
            logging.info("Page loaded successfully")
            
            # Check for specific error indicators (refined check)
            page_source = driver.page_source.lower()
            if "access denied" in page_source or "server error" in page_source:
                logging.error("Access denied or server error detected")
                return {'Reference': reference, 'Uso principal': 'Access Error', 'Superficie construida': 'Access Error'}
            
            # Handle potential cookie popup
            try:
                cookie_accept = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, 'cookie-accept'))  # Adjust ID based on inspection
                )
                cookie_accept.click()
                logging.info("Accepted cookie popup")
                time.sleep(2)
            except:
                logging.info("No cookie popup found or failed to accept")
            
            # Ensure the 'refcat2' tab is active
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, 'refcat2'))
            )
            tab = driver.find_element(By.ID, 'refcat2')
            driver.execute_script("arguments[0].classList.add('active');", tab)
            logging.info("Ensured 'refcat2' tab is active")
            
            # Wait for the reference input field to be visible and interactable
            ref_input = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, 'ct100_Contenido_txtRC2'))
            )
            logging.info("Found reference input field")
            WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.ID, 'ct100_Contenido_txtRC2'))
            )
            
            # Input the cadastral reference using JavaScript
            driver.execute_script(f"document.getElementById('ct100_Contenido_txtRC2').value = '{reference}';")
            logging.info(f"Set reference via JavaScript: {reference}")
            
            # Small delay to allow JavaScript validation
            time.sleep(1)
            
            # Verify the value was set
            entered_value = driver.execute_script("return document.getElementById('ct100_Contenido_txtRC2').value;")
            logging.info(f"Verified entered reference: {entered_value}")
            
            # Wait for and click the "Datos" button
            datos_button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.ID, 'ct100_Contenido_btnDatos'))
            )
            logging.info("Found 'Datos' button, attempting to click...")
            datos_button.click()
            logging.info("Clicked 'Datos' button")
            
            # Wait for the results page to load
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "detalleInmueble")]'))
            )
            logging.info("Results page loaded")
            
            # Extract "Uso principal"
            uso_principal = 'Not found'
            try:
                uso_element = driver.find_element(By.XPATH, '//td[contains(text(), "Uso principal")]/following-sibling::td')
                uso_principal = uso_element.text.strip()
            except:
                logging.warning(f"Uso principal not found for {reference}")
            
            # Extract "Superficie construida"
            superficie = 'Not found'
            try:
                superficie_element = driver.find_element(By.XPATH, '//td[contains(text(), "Superficie construida")]/following-sibling::td')
                superficie = superficie_element.text.strip()
            except:
                logging.warning(f"Superficie construida not found for {reference}")
            
            return {'Reference': reference, 'Uso principal': uso_principal, 'Superficie construida': superficie}
        
        except Exception as e:
            logging.error(f"Error processing {reference} on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                logging.info("Retrying after 5 seconds...")
                time.sleep(5)
                continue
            return {'Reference': reference, 'Uso principal': 'Error', 'Superficie construida': 'Error'}

# Process each reference
for ref in references:
    logging.info(f"Processing {ref}...")
    result = scrape_cadastre(ref)
    output_data.append(result)
    time.sleep(2)

# Save results to CSV
try:
    output_df = pd.DataFrame(output_data)
    output_df.to_csv('cadastre_results.csv', index=False)
    logging.info("Scraping complete. Results saved to cadastre_results.csv")
except Exception as e:
    logging.error(f"Failed to save results: {str(e)}")

# Close the driver
driver.quit()