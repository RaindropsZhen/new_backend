import requests
import hashlib
import time
from .models import Printer, Table
from django.utils import timezone
from googletrans import Translator
from collections import defaultdict
from datetime import datetime
from ipaddress import ip_address, ip_network
from core.globals import *

# SUSHI 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119
# DRINKS 188,189,190,191,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,213,214,215,216,217,266,267,268,269,270,271,272,273,274,275,276,277,278,279,280,281,282,283,284,285,286,287,288,289,290,291,292,293,294,295,296,297,298,299,300,301,302,303,304,305,306,307,308,309,310,311,312,313,314,315,316,322,323,324,325,326,327,328,329,330,331
# Desserts 172,173,174,175,176,177,178
# Chinese cuisine 140,141,142,143,144,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164
# 120,121,122,123,124,125,126,128,129,136,137,138,139,145,146,147

def generate_signature(user, user_key, timestamp):
    # Concatenate user, user_key, and timestamp
    combined_string = user + user_key + timestamp
    # Compute SHA1 hash and return as lowercase hexadecimal
    return hashlib.sha1(combined_string.encode()).hexdigest()

def api_print_request(user, user_key, sn,content):
    # Generate current UNIX timestamp
    timestamp = str(int(time.time()))
    
    # Generate signature
    signature = generate_signature(user, user_key, timestamp)
    
    # API endpoint
    url = "https://open.xpyun.net/api/openapi/xprinter/print"
    
    # Request body
    payload = {
        "sn": sn,
        "content": content,
        "copies": 1,
        "voice": 2,
        "user": user,
        "timestamp": timestamp,
        "sign": signature,
        "debug": "0",
        "mode":1,
        "expiresIn":10800 #如超过3个小时未打印将取消打印
    }
    
    # Make POST request
    response = requests.post(url, json=payload)
    
    return response.json()


def api_check_printer_request(user, user_key, sn):
    # Generate current UNIX timestamp
    timestamp = str(int(time.time()))
    
    # Generate signature
    signature = generate_signature(user, user_key, timestamp)
    
    # API endpoint
    url = "https://open.xpyun.net/api/openapi/xprinter/queryPrinterStatus"
    
    # Request body
    payload = {
        "sn": sn,
        "user": user,
        "timestamp":timestamp,
        "sign": signature,
    }

    
    # Make POST request
    response = requests.post(url, json=payload)
    
    return response.json()


def extract_name_quantity(details):
    name_quantity_list = []
    for item in details:
        name = item.get("name", "")
        quantity = item.get("quantity", "")
        name_quantity_list.append({"name": name, "quantity": quantity})
    return name_quantity_list

def format_list_as_string(name_quantity_list,font_size):
    if font_size =='B2':
        formatted_string = """
<L><LINE p="23" /><B>菜名</B><HT><B>数量</B><BR>
--------------------------------<BR>"""
        for item in name_quantity_list:
            name_to_print = item['name'].split('.')[0] + item['name_to_print']
            formatted_string += f"<B2>{name_to_print}<HT>{item['quantity']}<BR></B2><BR>"
            
        formatted_string += """--------------------------------<BR>
</L>"""
    elif font_size=="B1":
        formatted_string = """
<L><LINE p="23" /><B>菜名</B><HT><B>数量</B><BR>
--------------------------------<BR>"""
        for item in name_quantity_list:
            name_to_print = item['name'].split('.')[0] + item['name_to_print']
            formatted_string += f"<B>{name_to_print}<HT>{item['quantity']}<BR></B><BR>"
            
        formatted_string += """--------------------------------<BR>
</L>"""
    return formatted_string

def get_serial_number_by_menu_item(printers, item_id):
    try:
        for printer in printers:
            items_id = printer.menu_item_id
            if str(item_id) in items_id:
                return printer.serial_number
    except Exception as e:
        print(f"Error: {e}")
        return None


def update_printer_status(sn_id, new_status):
    printer = Printer.objects.get(serial_number=sn_id)
    printer.printer_status = new_status
    if new_status == 1:
        printer.printer_status_info = "在线,一切正常"
    elif new_status == 0:
        printer.printer_status_info = "离线，请检查网络连接"
    elif new_status == 2:
        printer.printer_status_info = "在线异常，请检查是否有打印纸"
    printer.save()



def update_last_ordering_time(place_id,table_number):
    # Obtain the Table object with the specified place_id
    table = Table.objects.get(place_id=place_id,table_number=table_number)

    # Retrieve the current time in Lisbon
    lisbon_time = timezone.localtime(timezone.now(), timezone=timezone.pytz.timezone('Europe/Lisbon'))
    # Extract hour, minute, and second components
    hour = lisbon_time.hour
    minute = lisbon_time.minute
    second = lisbon_time.second
    # Calculate seconds since midnight in Lisbon time
    lisbon_time_seconds_since_midnight = hour * 3600 + minute * 60 + second
    # Update the last_ordering_time field of the Table object with the current Lisbon time
    table.last_ordering_time = lisbon_time_seconds_since_midnight
    
    # Save the changes to the database
    table.save()

def handle_lunch_dinner_time(place,data):

    if data["ordering_timing"] == "lunch":
        lunch_time_start = place.lunch_time_start
        lunch_time_end = place.lunch_time_end
        dinne_time_start = None
        dinne_time_end = None
    elif data["ordering_timing"] =="dinner":
        lunch_time_start = None 
        lunch_time_end = None
        dinne_time_start = place.dinne_time_start
        dinne_time_end = place.dinne_time_end
    elif data["ordering_timing"] == "lunch_and_dinner":
        lunch_time_start = place.lunch_time_start        
        lunch_time_end = place.lunch_time_end
        dinne_time_start = place.dinne_time_start
        dinne_time_end = place.dinne_time_end

    return lunch_time_start,lunch_time_end,dinne_time_start,dinne_time_end

def translate_menu_name_description(data):

    translator = Translator()
    name_en = translator.translate(data['name'], dest='en').text
    name_pt = translator.translate(data['name'], dest='pt').text
    name_es = translator.translate(data['name'], dest='es').text

    description_en = translator.translate(data['description'], dest='en').text
    description_es = translator.translate(data['description'], dest='es').text
    description_pt = translator.translate(data['description'], dest='pt').text

    return name_en,name_pt,name_es,description_en,description_es,description_pt


def grouped_details(data,printers):

    translator = Translator()
    grouped_details_by_category = defaultdict(list)

    language = data["language"]
    if language == 'Português': 
        language = 'pt'
    elif language == 'English':
        language = 'en'
    elif language == 'Español':
        language = 'es'

    for detail in data["detail"]:
        item_id = str(detail["id"])
        grouped_details_by_category[item_id].append(detail)
    grouped_details_by_sn = defaultdict(list)

    for item_id, details_list in grouped_details_by_category.items():
        for detail in details_list:
            sn_id = get_serial_number_by_menu_item(printers, item_id)
            grouped_details_by_sn[sn_id].append(detail)

    return grouped_details_by_sn

def get_print_content(daily_order_id,data,details_list,font_size):

    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    content_header = """
<C><LINE p="15" />订单号:<B>{}</B><HT><BOLD>Mesa:</BOLD><B>{}</B><BR>
下单时间: <BOLD>{}</BOLD>
""".format(daily_order_id,data["table"],current_datetime)

    content_body = format_list_as_string(details_list,font_size)
    content = content_header + content_body 
    return content

# Utility function to get client IP
def get_client_ip(request):
    """Retrieve the client's IP address from the request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    print(x_forwarded_for)
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# Utility function to check if IP is allowed
def is_ip_allowed(ip, allowed_ips):
    """Check if the IP address is within the allowed range."""
    client_ip = ip_address(ip)
    for ip_range in allowed_ips:
        if client_ip in ip_network(ip_range):
            return True
    return False