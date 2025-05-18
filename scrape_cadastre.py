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
import re
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize the Chrome driver (non-headless for debugging)
options = Options()
# Comment out headless mode for debugging
# options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shorp-usage')
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
            
            # Check for specific error indicators
            page_source = driver.page_source.lower()
            if "access denied" in page_source or "server error" in page_source:
                logging.error("Access denied or server error detected")
                return {'Reference': reference, 'Uso principal': 'Access Error', 'Superficie construida': 'Access Error', 'Año construcción': 'Access Error'}
            
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
            
            # Wait for the tab list to be present
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.ID, 'selectMode'))
            )
            logging.info("Found tab list 'selectMode'")
            
            # Debug: Log all tab links with their href and text
            tab_links = driver.find_elements(By.XPATH, '//ul[@id="selectMode"]//a')
            for link in tab_links:
                href = link.get_attribute('href') or "No href"
                text = link.text.strip() or "No text"
                logging.info(f"Tab link - href: {href}, text: {text}")
            
            # Try multiple methods to click the 'refcat2' tab
            tab_link = None
            try:
                # Method 1: By href
                tab_link = WebDriverWait(driver, 60).until(
                    EC.element_to_be_clickable((By.XPATH, '//ul[@id="selectMode"]//a[contains(@href, "refcat2")]'))
                )
                driver.execute_script("arguments[0].click();", tab_link)
                logging.info("Clicked 'refcat2' tab to activate (via href)")
            except:
                logging.warning("Failed to click 'refcat2' tab via href, trying by text...")
                try:
                    # Method 2: By text "Referencia Catastral"
                    tab_link = WebDriverWait(driver, 60).until(
                        EC.element_to_be_clickable((By.XPATH, '//ul[@id="selectMode"]//a[contains(text(), "Referencia Catastral")]'))
                    )
                    driver.execute_script("arguments[0].click();", tab_link)
                    logging.info("Clicked 'refcat2' tab to activate (via text)")
                except:
                    logging.warning("Failed to click 'refcat2' tab via text, trying by role and href...")
                    # Method 3: By role and href
                    tab_link = WebDriverWait(driver, 60).until(
                        EC.element_to_be_clickable((By.XPATH, '//ul[@id="selectMode"]//a[@role="tab" and contains(@href, "refcat2")]'))
                    )
                    driver.execute_script("arguments[0].click();", tab_link)
                    logging.info("Clicked 'refcat2' tab to activate (via role and href)")
            
            # Wait for the tab panel to be active
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.XPATH, '//div[@id="refcat2" and contains(@class, "active")]'))
            )
            logging.info("Confirmed 'refcat2' tab is active")
            
            # Wait for the reference input field to be visible and interactable
            ref_input = WebDriverWait(driver, 120).until(
                EC.presence_of_element_located((By.ID, 'ctl00_Contenido_txtRC2'))
            )
            logging.info("Found reference input field")
            WebDriverWait(driver, 120).until(
                EC.element_to_be_clickable((By.ID, 'ctl00_Contenido_txtRC2'))
            )
            logging.info("Input field is clickable")
            
            # Debug: Check if the field is enabled
            is_enabled = driver.execute_script("return document.getElementById('ctl00_Contenido_txtRC2').disabled === false;")
            logging.info(f"Input field is enabled: {is_enabled}")
            
            # Input the cadastral reference using multiple methods
            try:
                # Method 1: JavaScript to set value
                driver.execute_script(f"document.getElementById('ctl00_Contenido_txtRC2').value = '{reference}';")
                logging.info(f"Attempted to set reference via JavaScript: {reference}")
                time.sleep(1)  # Allow time for event handlers
            except Exception as e:
                logging.error(f"JavaScript set failed: {str(e)}")
            
            # Method 2: Clear and send keys as fallback
            try:
                input_field = driver.find_element(By.ID, 'ctl00_Contenido_txtRC2')
                input_field.clear()
                input_field.send_keys(reference)
                logging.info(f"Attempted to set reference via send_keys: {reference}")
                time.sleep(1)  # Allow time for event handlers
            except Exception as e:
                logging.error(f"Send_keys failed: {str(e)}")
            
            # Verify the value was set
            entered_value = driver.execute_script("return document.getElementById('ctl00_Contenido_txtRC2').value;")
            logging.info(f"Verified entered reference: {entered_value}")
            
            # Check for validation errors
            try:
                error_div = driver.find_element(By.ID, 'DivErrorRC')
                if error_div.is_displayed():
                    error_message = error_div.text
                    logging.error(f"Validation error detected: {error_message}")
                    return {'Reference': reference, 'Uso principal': 'Validation Error', 'Superficie construida': error_message, 'Año construcción': 'Validation Error'}
            except:
                logging.info("No validation error detected")
            
            # Wait for and click the "Datos" button
            datos_button = WebDriverWait(driver, 120).until(
                EC.element_to_be_clickable((By.ID, 'ctl00_Contenido_btnDatos'))
            )
            logging.info("Found 'Datos' button, attempting to click...")
            driver.execute_script("arguments[0].click();", datos_button)
            logging.info("Clicked 'Datos' button")
            
            # Wait for the results page to load by looking for "Uso principal"
            WebDriverWait(driver, 120).until(
                EC.presence_of_element_located((By.XPATH, '//span[contains(text(), "Uso principal")]'))
            )
            logging.info("Results page loaded (Uso principal detected)")
            
            # Debug: Log part of the page source to inspect
            page_source_snippet = driver.page_source[:5000]  # Limit to first 5000 chars for readability
            logging.info(f"Page source snippet: {page_source_snippet}")
            
            # Extract "Uso principal"
            uso_principal = 'Not found'
            try:
                uso_element = WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, '//span[contains(text(), "Uso principal")]/following-sibling::div//label'))
                )
                uso_principal = uso_element.text.strip()
                logging.info(f"Extracted Uso principal: {uso_principal}")
            except:
                logging.warning(f"Uso principal not found for {reference}")
            
            # Extract "Superficie construida"
            superficie = 'Not found'
            try:
                superficie_element = WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, '//span[contains(text(), "Superficie construida")]/following-sibling::div//label'))
                )
                # Get the raw HTML and extract the numeric value
                superficie_html = superficie_element.get_attribute('innerHTML')
                # Use regex to extract the number before "m"
                match = re.search(r'(\d+\.?\d*) m', superficie_html)
                if match:
                    superficie = f"{match.group(1)} m²"
                else:
                    superficie = superficie_element.text.strip().replace('²', '').replace('2', '²') + ' m²'
                logging.info(f"Extracted Superficie construida: {superficie}")
            except:
                logging.warning(f"Superficie construida not found for {reference}")
            
            # Extract "Año construcción"
            ano_construccion = 'Not found'
            try:
                ano_element = WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, '//span[contains(text(), "Año construcción")]/following-sibling::div//label'))
                )
                ano_construccion = ano_element.text.strip()
                logging.info(f"Extracted Año construcción: {ano_construccion}")
            except:
                logging.warning(f"Año construcción not found for {reference}")
            
            return {'Reference': reference, 'Uso principal': uso_principal, 'Superficie construida': superficie, 'Año construcción': ano_construccion}
        
        except Exception as e:
            logging.error(f"Error processing {reference} on attempt {attempt + 1}: {str(e)}")
            # Debug: Log visible elements and page source
            try:
                inputs = driver.find_elements(By.XPATH, '//input')
                logging.info(f"Visible input elements: {[elem.get_attribute('id') for elem in inputs]}")
                page_source_snippet = driver.page_source[:5000]
                logging.info(f"Page source snippet after error: {page_source_snippet}")
            except:
                logging.info("Could not retrieve visible elements or page source")
            if attempt < max_retries - 1:
                logging.info("Retrying after 5 seconds...")
                time.sleep(5)
                continue
            return {'Reference': reference, 'Uso principal': 'Error', 'Superficie construida': 'Error', 'Año construcción': 'Error'}

# Process each reference
for ref in references:
    logging.info(f"Processing {ref}...")
    result = scrape_cadastre(ref)
    output_data.append(result)
    logging.info(f"Completed processing {ref}: Uso principal={result['Uso principal']}, Superficie construida={result['Superficie construida']}, Año construcción={result['Año construcción']}")
    time.sleep(2)  # Small delay before reloading the page

# Save results to CSV
output_file = 'cadastre_results.csv'
try:
    if os.path.exists(output_file):
        # Append to existing file without writing headers
        output_df = pd.DataFrame(output_data)
        output_df.to_csv(output_file, mode='a', header=False, index=False)
        logging.info("Results appended to cadastre_results.csv")
    else:
        # Create new file with headers
        output_df = pd.DataFrame(output_data)
        output_df.to_csv(output_file, mode='w', header=True, index=False)
        logging.info("Results saved to new cadastre_results.csv")
except Exception as e:
    logging.error(f"Failed to save results: {str(e)}")

# Close the driver
driver.quit()