import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os # Added for directory creation

BASE_URL = "https://eurocarveiculos.com"
OUTPUT_DIR = "dados" # Define output directory
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "estoque_eurocar.json") # Define full output path

def parse_price(price_str):
    if not price_str:
        return 0.0
    cleaned_price = re.sub(r"[R$\s]", "", price_str)
    if "," in cleaned_price and "." in cleaned_price:
        if cleaned_price.rfind(".") < cleaned_price.rfind(","):
            cleaned_price = cleaned_price.replace(".", "").replace(",", ".")
        else:
            cleaned_price = cleaned_price.replace(",", "")
    elif "," in cleaned_price:
        cleaned_price = cleaned_price.replace(",", ".")
    try:
        return float(cleaned_price)
    except ValueError:
        print(f"  Could not parse price: {price_str} (cleaned: {cleaned_price})")
        return 0.0

def parse_km(km_str):
    if not km_str:
        return 0
    cleaned_km = re.sub(r"[^0-9]", "", km_str)
    try:
        return int(cleaned_km)
    except ValueError:
        print(f"  Could not parse km: {km_str}")
        return 0

def get_vehicle_details(detail_url):
    print(f"Fetching details from: {detail_url}")
    vehicle_data = {
        "link_details": detail_url,
        "name": "N/A", "brand": "N/A", "model_base": "N/A", "version_details": "",
        "price": 0.0, "year": "N/A", "km": 0,
        "transmission_type": "N/A", "fuel_type": "N/A", "color": "N/A", "doors": 0,
        "options": [], "description": "", "main_image_url": "", "photos": []
    }
    try:
        response = requests.get(detail_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")

        title_tag = soup.find("h1", class_="font-weight-bold") or soup.find("h1", class_="mb-0") or soup.select_one("div.container h1")
        if title_tag:
            full_title_text = title_tag.text.strip()
            vehicle_data["name"] = re.split(r"\s+em\s+\w+\s*-\s*Eurocar Multimarcas", full_title_text, flags=re.IGNORECASE)[0].strip()
        else:
            title_tag_fallback = soup.find("title")
            if title_tag_fallback:
                full_title = title_tag_fallback.text.strip()
                vehicle_data["name"] = re.split(r"\s+em\s+\w+\s*-\s*Eurocar Multimarcas", full_title, flags=re.IGNORECASE)[0].strip()
        
        if vehicle_data["name"] != "N/A":
            name_str = vehicle_data["name"]
            name_str = re.sub(r"\s+\d{4}/\d{4}\s+-", "", name_str).strip()
            name_str = re.sub(r"\s+\d{4}\s+-", "", name_str).strip()
            name_str = re.sub(r"\s+[\d\.]+KM", "", name_str, flags=re.IGNORECASE).strip()
            vehicle_data["name"] = name_str

        price_tag = soup.find("p", class_="venda") or \
                    soup.select_one("div.preco-veiculo p.font-weight-bold, div.price-vehicle p.font-weight-bold") or \
                    soup.find("p", string=re.compile(r"R\$")) or \
                    soup.select_one("div.price span.value, span.preco-valor")
        if price_tag:
            price_text_content = price_tag.text.strip()
            match_price = re.search(r"R\$\s*([\d\.,]+)", price_text_content)
            if match_price:
                vehicle_data["price"] = parse_price(match_price.group(1))

        year_el = soup.select_one("div.info-veiculo-ano p, li.ano-veiculo, span.car-info-year, div.detalhes-veiculo-ano strong")
        km_el = soup.select_one("div.info-veiculo-km p, li.km-veiculo, span.car-info-km, div.detalhes-veiculo-km strong")
        if year_el: vehicle_data["year"] = year_el.text.strip()
        if km_el: vehicle_data["km"] = parse_km(km_el.text.strip())

        ficha_tecnica_heading = soup.find(lambda tag: tag.name in ["h2", "h3", "h4", "h5", "strong"] and "FICHA TÉCNICA" in tag.text.upper())
        if ficha_tecnica_heading:
            current_element = ficha_tecnica_heading.find_next_sibling()
            ficha_items_container = None
            while current_element:
                if current_element.name == "div" and (current_element.find("strong") or current_element.find_all("div", class_=re.compile(r"col"))):
                    ficha_items_container = current_element
                    break
                if current_element.name in ["h2", "h3", "h4", "h5"]: break
                current_element = current_element.find_next_sibling()
            
            if ficha_items_container:
                potential_items = ficha_items_container.find_all("div", class_=re.compile(r"col-md-2|col-sm-4|col-xs-6|item-ficha"))
                if not potential_items: potential_items = ficha_items_container.find_all(lambda tag: tag.name == "div" and tag.find("strong"), recursive=False)
                if not potential_items: potential_items = ficha_items_container.find_all("div")

                for item_div in potential_items:
                    strong_tag = item_div.find("strong")
                    if strong_tag:
                        label = strong_tag.text.strip().lower()
                        value = "".join(sibling.strip() for sibling in strong_tag.next_siblings if isinstance(sibling, str) and sibling.strip())
                        if not value: value = item_div.text.replace(strong_tag.text, "").strip();
                        if value.startswith(":"): value = value[1:].strip()
                        if not value and item_div.find_all("span"): value_span = strong_tag.find_next_sibling("span");
                        if value_span: value = value_span.text.strip()
                        if not value: continue
                        if "ano" in label and vehicle_data["year"] == "N/A": vehicle_data["year"] = value
                        elif "km" in label and vehicle_data["km"] == 0: vehicle_data["km"] = parse_km(value)
                        elif "câmbio" in label: vehicle_data["transmission_type"] = value
                        elif "combustível" in label: vehicle_data["fuel_type"] = value
                        elif "cor" in label: vehicle_data["color"] = value
                        elif "portas" in label: vehicle_data["doors"] = int(re.sub(r"[^0-9]", "", value) or 0)
        
        if vehicle_data["year"] == "N/A" or vehicle_data["km"] == 0:
            year_km_p_tag = soup.find("p", class_="text-muted", string=re.compile(r"(\d{4}/\d{4}|\d{4}).*[\d\.]+\s*KM", re.I))
            if not year_km_p_tag: year_km_p_tag = soup.find("p", class_="font-weight-normal", string=re.compile(r"(\d{4}/\d{4}|\d{4}).*[\d\.]+\s*KM", re.I))
            if year_km_p_tag:
                text = year_km_p_tag.text.strip()
                year_m = re.search(r"(\d{4}/\d{4}|\d{4})", text)
                km_m = re.search(r"([\d\.]+)\s*KM", text, re.I)
                if year_m and vehicle_data["year"] == "N/A": vehicle_data["year"] = year_m.group(1)
                if km_m and vehicle_data["km"] == 0: vehicle_data["km"] = parse_km(km_m.group(1))

        opcionais_heading = soup.find(lambda tag: tag.name in ["h2", "h3", "h4", "h5", "strong"] and "OPCIONAIS" in tag.text.upper())
        if opcionais_heading:
            op_container = opcionais_heading.find_next_sibling("ul") or opcionais_heading.find_next_sibling("div", class_=re.compile(r"options|features"))
            if op_container:
                if op_container.name == "ul":
                    vehicle_data["options"] = [li.text.strip() for li in op_container.find_all("li") if li.text.strip()]
                elif op_container.name == "div":
                    vehicle_data["options"] = [div.text.strip() for div in op_container.find_all("div", class_=re.compile(r"item|option")) if div.text.strip()]
                    if not vehicle_data["options"]: vehicle_data["options"] = [tag.text.strip() for tag in op_container.find_all(["span", "p", "li"]) if tag.text.strip()]

        desc_tag = soup.select_one("div#collapseDescricao div.card-body, div.description-vehicle, div.vehicle-description, section#descricao p, div.car-description-text")
        if desc_tag: vehicle_data["description"] = desc_tag.text.strip()

        main_img_tag = soup.select_one("div.carousel-inner div.carousel-item.active img, figure.zoom img, img.showcase-image, div.fotorama__stage__frame img.fotorama__img, img#img-destaque-veiculo") or soup.select_one("div.item-carro-imagem-destaque img, div.details-gallery-main img")
        if main_img_tag:
            img_src = main_img_tag.get("src") or main_img_tag.get("data-src")
            if img_src: vehicle_data["main_image_url"] = img_src if img_src.startswith("http") else BASE_URL + img_src

        photo_tags = soup.select("div.carousel-inner div.carousel-item img, div.gallery-thumbs img, div.slick-slide img, div.fotorama__nav__frame img, a.fancybox img, div.thumbnails-list img")
        for img_tag in photo_tags:
            img_src = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("href")
            if img_src and (any(ext in img_src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"])):
                full_img_src = img_src if img_src.startswith("http") else BASE_URL + img_src
                if full_img_src not in vehicle_data["photos"]: vehicle_data["photos"].append(full_img_src)
        if not vehicle_data["photos"] and vehicle_data["main_image_url"]: vehicle_data["photos"].append(vehicle_data["main_image_url"])
        vehicle_data["photos"] = list(set(vehicle_data["photos"])) 

        if vehicle_data["name"] != "N/A":
            name_str = vehicle_data["name"]
            parts = name_str.split(" ", 1)
            vehicle_data["brand"] = parts[0] if len(parts) > 0 else "N/A"
            model_and_version = parts[1] if len(parts) > 1 else name_str
            common_models = sorted(["ONIX PLUS", "ONIX", "HB20", "MOBI", "NOVA SAVEIRO", "SAVEIRO", "COROLLA", "GOL", "PARTNER", "S10", "RENEGADE", "TIGUAN ALLSPAC", "TIGUAN", "STRADA", "KWID", "POLO", "VIRTUS", "CRONOS", "ARGO", "TORO", "COMPASS", "CLIO", "CITY", "CRUZE", "SENTRA", "CLASSIC", "FOX", "FOCUS", "IX35"], key=len, reverse=True)
            model_base_found = "N/A"
            version_details_found = model_and_version
            for model in common_models:
                if model_and_version.upper().startswith(model + " ") or model_and_version.upper() == model:
                    model_base_found = model
                    version_details_found = model_and_version[len(model):].strip()
                    break
            if model_base_found == "N/A":
                if " " in model_and_version: model_parts = model_and_version.split(" ", 1); model_base_found = model_parts[0]; version_details_found = model_parts[1] if len(model_parts) > 1 else ""
                else: model_base_found = model_and_version; version_details_found = ""
            vehicle_data["model_base"] = model_base_found
            vehicle_data["version_details"] = version_details_found

        print(f"  Successfully parsed: {vehicle_data.get('name')} - Price: {vehicle_data.get('price')} - Year: {vehicle_data.get('year')} - KM: {vehicle_data.get('km')} - Cambio: {vehicle_data.get('transmission_type')} - Cor: {vehicle_data.get('color')} - Portas: {vehicle_data.get('doors')}")
        return vehicle_data

    except requests.exceptions.RequestException as e:
        print(f"  Error fetching {detail_url}: {e}")
    except Exception as e:
        print(f"  Error parsing {detail_url}: {e}")
    return None

def scrape_website():
    stock_list_url = f"{BASE_URL}/multipla"
    print(f"Fetching stock list from: {stock_list_url}")
    vehicle_detail_urls = set()
    processed_vehicle_names_on_page = set()
    try:
        response = requests.get(stock_list_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")
        listing_containers = soup.select("div.card-veiculo, div.item-carro, article.vehicle-item, div.product-item, div.box-veiculo")
        links_found = []
        if listing_containers:
            print(f"  Found {len(listing_containers)} potential listing containers.")
            for container in listing_containers:
                link_tag = container.find("a", href=re.compile(r"/carros/.+\.html"))
                if not link_tag: link_tag = container.find("a", href=True)
                if link_tag:
                    name_tag = container.find(["h2","h3","h4","p"], class_=re.compile(r"(title|name|modelo)", re.I))
                    vehicle_name_on_page = name_tag.text.strip() if name_tag else str(link_tag)
                    if vehicle_name_on_page not in processed_vehicle_names_on_page:
                        href = link_tag.get("href")
                        if href and ".html" in href and "/carros/" in href:
                            links_found.append(link_tag)
                            processed_vehicle_names_on_page.add(vehicle_name_on_page)
        else:
            print("  No standard listing containers found. Falling back to broader link search.")
            links_found = soup.find_all("a", href=re.compile(r"/carros/.+\.html"))
        print(f"  Found {len(links_found)} link tags potentially leading to vehicle details after container search.")
        for link_tag in links_found:
            href = link_tag.get("href")
            if href:
                full_url = BASE_URL + href if not href.startswith("http") else href
                if ".html" in full_url and "/carros/" in full_url and not full_url.endswith(("/multipla", "/multipla/")) and "?" not in full_url and "#" not in full_url:
                    vehicle_detail_urls.add(full_url)
        print(f"Found {len(vehicle_detail_urls)} unique vehicle detail URLs to process from {stock_list_url}.")
    except Exception as e:
        print(f"Error during stock list processing: {e}")
    if not vehicle_detail_urls: print("No vehicle detail URLs found. Exiting."); return []
    all_vehicles_data = []
    for i, url in enumerate(sorted(list(vehicle_detail_urls))):
        print(f"Processing vehicle {i+1}/{len(vehicle_detail_urls)}: {url}")
        details = get_vehicle_details(url)
        if details: all_vehicles_data.append(details)
        time.sleep(0.55) 
    return all_vehicles_data

if __name__ == "__main__":
    print("Starting Eurocar Scraper...")
    # Create output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created directory: {OUTPUT_DIR}")

    scraped_data = scrape_website()
    if scraped_data:
        try:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(scraped_data, f, ensure_ascii=False, indent=4)
            print(f"Scraping complete. Data saved to {OUTPUT_FILE}")
            print(f"Total vehicles scraped: {len(scraped_data)}")
        except IOError as e: print(f"Error writing to file {OUTPUT_FILE}: {e}")
    else: print("No data was scraped or an error occurred.")

