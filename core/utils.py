import requests
import hashlib
import time
from .models import Printer, Table
from django.utils import timezone
from googletrans import Translator
from collections import defaultdict
from datetime import datetime


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

def format_list_as_string(name_quantity_list):
    formatted_string = """
<L><LINE p="23" /><B>菜名</B><HT><B>数量</B><BR>
--------------------------------<BR>"""
    for item in name_quantity_list:
        name_to_print = item['name_to_print'] + item['name']
        formatted_string += f"<B2>{name_to_print}<HT>{item['quantity']}<BR></B2><BR>"
        
    formatted_string += """--------------------------------<BR>
</L>"""
    return formatted_string

def get_serial_number_by_category(printers, category_id):
    try:
        for printer in printers:
            categories_id = printer.category
            if str(category_id) in categories_id:
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

# def update_last_ordering_time(place_id, table_number):
#     # Obtain the Table object with the specified place_id
#     table = Table.objects.get(place_id=place_id, table_number=table_number)

#     # Retrieve the current time in the local timezone
#     current_time = timezone.localtime(timezone.now())

#     # Calculate seconds since midnight in local time
#     current_time_seconds_since_midnight = current_time.timestamp() % (24 * 3600)
#     print(current_time_seconds_since_midnight)
#     # Update the last_ordering_time field of the Table object with the current local time
#     table.last_ordering_time = current_time_seconds_since_midnight
    
#     # Save the changes to the database
#     table.save()
    
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

def grouped_details(data,printers,grouped_comments_dict):

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
        category_id = detail["category"]
        if category_id in grouped_comments_dict.keys():
            comment = grouped_comments_dict[category_id]
            comment_translated  = translator.translate(comment, src=language,dest='zh-CN').text
            detail["comment"] = "原文:{}, 译文:{}".format(comment,comment_translated)
        else:
            detail["comment"] = {}
        grouped_details_by_category[category_id].append(detail)

    grouped_details_by_sn = defaultdict(list)
    for category_id, details_list in grouped_details_by_category.items():
        for detail in details_list:
            sn_id = get_serial_number_by_category(printers, category_id)
            grouped_details_by_sn[sn_id].append(detail)

    return grouped_details_by_sn

def get_print_content(daily_order_id,data,details_list):

    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content_header = """
<C><LINE p="15" />订单号:<B>{}</B><HT><BOLD>Mesa:</BOLD><B>{}</B><BR>
下单时间: <BOLD>{}</BOLD>
""".format(daily_order_id,data["table"],current_datetime)

    content_body = format_list_as_string(details_list)
    content_comment = details_list[0]["comment"]
    if content_comment == {}:
        content_comment = ""
        content = content_header + content_body + content_comment
    else:
        content_comment = """
<BOLD>备注: </BOLD>
"""+content_comment
        
        content = content_header + content_body + content_comment  
    return content
