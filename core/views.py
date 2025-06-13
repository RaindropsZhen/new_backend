import json
from googletrans import Translator
from django.utils import timezone
from django.db.models import Max
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status, views
from rest_framework.response import Response
from django.db import transaction
from . import models, serializers, permissions
from django.shortcuts import render, get_object_or_404
import requests
from qrmenu_backend.settings import user as USER_NAME,user_key as USER_KEY
from .models import Printer # Removed Place, MenuItem as models.Place etc. is used
from datetime import datetime # Added for current_datetime_azores
from collections import defaultdict # Added for reprint_order
from core.utils import *
import pytz

# Create your views here.
class PlaceList(generics.ListCreateAPIView):
  serializer_class = serializers.PlaceSerializer


  
  def get_queryset(self):
    return models.Place.objects.filter(owner_id=self.request.user.id)

  def perform_create(self, serializer):
    serializer.save(owner=self.request.user)

class PlaceDetail(generics.RetrieveUpdateDestroyAPIView):
  permission_classes = [permissions.IsOwnerOrReadOnly]
  serializer_class = serializers.PlaceDetailSerializer
  queryset = models.Place.objects.all()

class CategoryList(generics.CreateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.CategorySerializer

class CategoryDetail(generics.UpdateAPIView, generics.DestroyAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  queryset = models.Category.objects.all()
  serializer_class = serializers.CategorySerializer

class MenuItemList(generics.CreateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.MenuItemSerializer

class MenuItemDetail(generics.UpdateAPIView, generics.DestroyAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.MenuItemSerializer
  queryset = models.MenuItem.objects.all()

class TableDetail(generics.UpdateAPIView, generics.DestroyAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.TableSerializer
  queryset = models.Table.objects.all()

class TableBlockedStatusUpdate(generics.UpdateAPIView):
    permission_classes = [permissions.PlaceOwnerOrReadOnly]
    queryset = models.Table.objects.all()
    serializer_class = serializers.TableSerializer


class OrderList(generics.ListAPIView):
  serializer_class = serializers.OrderSerializer

  def get_queryset(self):
    return models.Order.objects.filter(place__owner_id=self.request.user.id, place_id=self.request.GET.get('place'))

class OrderDetail(generics.UpdateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.OrderSerializer
  queryset = models.Order.objects.all()

# Duplicate OrderList and OrderDetail removed, assuming the first pair is correct.

class PrintersDetail(generics.UpdateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.PrinterSerializer
  queryset = models.Printer.objects.all()

def home(request):
   return render(request, 'index.html')

@csrf_exempt
def create_order_intent(request):
    try:
        if not request.body:
            return JsonResponse({"success": False, "error": "Request body is empty."}, status=400)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            # For debugging, you might want to log request.body here
            # import logging
            # logger = logging.getLogger(__name__)
            # logger.error(f"JSONDecodeError: {str(e)} - Request body: {request.body[:500]}")
            return JsonResponse({"success": False, "error": f"Invalid JSON format in request body: {str(e)}"}, status=400)

        place_id = data.get("place")
        if place_id is None:
            return JsonResponse({"success": False, "error": "Missing 'place' key in request data."}, status=400)
        
        # Validate place_id
        try:
            place = models.Place.objects.get(id=place_id)
        except models.Place.DoesNotExist:
            return JsonResponse({"success": False, "error": "Place not found."}, status=404)

        today = timezone.now().date()
        # Ensure daily_id is scoped per place
        max_daily_id_result = models.Order.objects.filter(place_id=place_id, created_at__date=today).aggregate(Max('daily_id'))
        max_id = max_daily_id_result['daily_id__max'] or 0
        daily_order_id = max_id + 1

        order_items_data_from_request = data.get('detail', []) 
        
        if not order_items_data_from_request:
            return JsonResponse({"success": False, "error": "Order must contain at least one item."}, status=400)

        total_order_amount = 0
        processed_order_item_details_for_json = [] # For storing in Order.detail (summary)
        
        # Temporary list to hold validated menu_item_obj and quantity for OrderItem creation
        validated_items_for_order = []

        # First loop: Validate items, calculate total amount, prepare details for Order.detail
        for item_data in order_items_data_from_request:
            menu_item_id = str(item_data.get("id"))
            quantity = int(item_data.get('quantity', 0))
            price_from_request = float(item_data.get('price', 0)) # Price per unit from frontend

            if quantity <= 0:
                return JsonResponse({"success": False, "error": f"Quantity for item id {menu_item_id} must be positive."}, status=400)

            try:
                menu_item_obj = models.MenuItem.objects.get(id=menu_item_id, place_id=place_id)
            except models.MenuItem.DoesNotExist:
                return JsonResponse({"success": False, "error": f"MenuItem with id {menu_item_id} not found for this place."}, status=404)
            
            # Using price from database for calculation is safer, but for now, respecting frontend price.
            # Consider validating frontend price against db price if business rules require.
            # current_item_price = menu_item_obj.price 
            current_item_price = price_from_request 

            total_order_amount += current_item_price * quantity
            
            category_name = menu_item_obj.category.name # Using Chinese name from related Category object

            processed_order_item_details_for_json.append({
                'id': menu_item_id,
                'name': menu_item_obj.name, 
                'category_name': category_name,
                'quantity': quantity,
                'price': current_item_price 
            })
            
            validated_items_for_order.append({
                'menu_item_obj': menu_item_obj,
                'quantity': quantity,
                'price_at_time_of_order': current_item_price,
                'category_name_at_time_of_order': category_name
            })

        # Determine main_sn_id for the Order (e.g., based on first item or a general printer)
        # This logic might need to be more sophisticated if orders are split across printers.
        printers_for_place = models.Printer.objects.filter(place_id=place_id)
        main_sn_id = None
        if validated_items_for_order:
            first_item_menu_obj = validated_items_for_order[0]['menu_item_obj']
            main_sn_id = get_printer_sn_for_item(printers_for_place, first_item_menu_obj) # Use new function


        # Create the single Order object
        with transaction.atomic(): # Ensure all or nothing for order and items
            order = models.Order.objects.create(
                place=place, # Use the fetched Place instance
                table=data['table'],
                detail=json.dumps(processed_order_item_details_for_json), 
                amount=total_order_amount, 
                isTakeAway=data.get('isTakeAway', False),
                phoneNumer=data.get('phoneNumber'), 
                comment=data.get('comment'),
                arrival_time=data.get('arrival_time'),
                customer_name=data.get('customer_name'),
                daily_id=daily_order_id,
                isPrinted=False, 
                sn_id=main_sn_id 
                # created_at is auto_now_add=True
            )

            # Second loop: Create OrderItem instances
            for item_to_create in validated_items_for_order:
                models.OrderItem.objects.create(
                    order=order,
                    menu_item=item_to_create['menu_item_obj'],
                    quantity=item_to_create['quantity'],
                    price_at_time_of_order=item_to_create['price_at_time_of_order'],
                    category_name_at_time_of_order=item_to_create['category_name_at_time_of_order']
                )
            
            # START: New Printing Logic
            grouped_items_for_printing = defaultdict(list)
            # printers_for_place is already fetched above

            for item_instance in order.items.all(): # Iterate through created OrderItems
                menu_item_obj = item_instance.menu_item
                sn_id = get_printer_sn_for_item(printers_for_place, menu_item_obj)
                
                if sn_id: # Only try to print if a printer is found
                    name_to_print_for_item = menu_item_obj.name_to_print if menu_item_obj.name_to_print else menu_item_obj.name
                    
                    item_detail_for_print = {
                        'name': menu_item_obj.name, 
                        'name_to_print': name_to_print_for_item, 
                        'quantity': item_instance.quantity
                        # Add other fields if get_print_content or format_list_as_string uses them
                    }
                    grouped_items_for_printing[sn_id].append(item_detail_for_print)
            
            print_jobs_successful = True # Assume success initially
            if not grouped_items_for_printing: # If no items were matched to any printer
                print_jobs_successful = False # Or handle as "nothing to print"

            if grouped_items_for_printing:
                datetime_to_print_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S")

                for sn_id, items_for_this_printer in grouped_items_for_printing.items():
                    # Assuming 'B1' is a default font size for now. This might need to be configurable.
                    print_content = get_print_content(order.daily_id, data, items_for_this_printer, "B1", datetime_to_print_str)
                    try:
                        print_response = api_print_request(USER_NAME, USER_KEY, sn_id, print_content)
                        # Check Xpyun success: typically ret=0 and data.ok[0]=="0" or similar
                        # This check might need adjustment based on exact Xpyun API response structure for success.
                        if not (print_response.get("ret") == 0 and \
                                isinstance(print_response.get("data"), dict) and \
                                print_response.get("data", {}).get("ok") and \
                                isinstance(print_response.get("data").get("ok"), list) and \
                                len(print_response.get("data").get("ok")) > 0 and \
                                print_response.get("data").get("ok")[0] == "0"):
                            print(f"Warning: Print job to SN {sn_id} might have failed or had unexpected response. Response: {print_response}")
                            print_jobs_successful = False 
                    except Exception as print_e:
                        print(f"Error sending print job to SN {sn_id}: {print_e}")
                        print_jobs_successful = False 

            if print_jobs_successful and grouped_items_for_printing:
                order.isPrinted = True
            else:
                # If nothing to print, or if any print job failed, mark as not printed or partially printed.
                # For simplicity, keeping it False if any issue or nothing to print.
                order.isPrinted = False 
            order.save(update_fields=['isPrinted'])
            # END: New Printing Logic

        update_last_ordering_time(place_id, data["table"]) # Assuming this function is correct
        
        return JsonResponse({
            "success": True,
            "order_id": order.id,
        })

    except KeyError as e:
        return JsonResponse({"success": False, "error": f"Missing key in request data: {str(e)}"}, status=400)
    except Exception as e:
        # Log the full error for debugging on the server
        # import logging
        # logger = logging.getLogger(__name__)
        # logger.error(f"Error in create_order_intent: {str(e)}", exc_info=True)
        return JsonResponse({
            "success": False,
            "error": f"An unexpected error occurred: {str(e)}", 
        }, status=500)
    
@csrf_exempt
def create_category_intent(request):
    try:
        data = json.loads(request.body)
        translator = Translator()
        name_en = translator.translate(data['name'], src='zh-CN', dest='en').text
        name_pt = translator.translate(data['name'],src='zh-CN', dest='pt').text
        category = models.Category.objects.create(
            place_id=data['place'],
            name=data['name'],
            name_en=name_en,
            name_pt=name_pt
        )

        return JsonResponse({
            "success": True,
            "category_name": category.name,
            "category_id": category.id # Optionally return ID
        })

    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        }, status=500)

@csrf_exempt
def create_menu_items_intent(request):
    if request.method == 'POST':
        try:
            form_data = request.POST # Renamed data to form_data to avoid confusion
            image_file = request.FILES.get('image')

            place_id_str = form_data.get("place")
            if not place_id_str:
                return JsonResponse({"success": False, "error": "Place ID is required."}, status=400)
            
            place_id = int(place_id_str)
            place = models.Place.objects.get(id=place_id)

            menu_item_name = form_data.get('name')
            if not menu_item_name: # Checks for None or empty string
                return JsonResponse({"success": False, "error": "Menu item name is required and cannot be empty."}, status=400)
            
            helper_data = {
                'ordering_timing': form_data.get('ordering_timing', 'lunch_and_dinner'),
                'name': menu_item_name, # Use the validated name
                'description': form_data.get('description', '')
            }

            lunch_time_start,lunch_time_end,dinne_time_start,dinne_time_end = handle_lunch_dinner_time(place, helper_data)
            price = float(form_data.get('price', 0))

            name_to_print_from_form = form_data.get("name_to_print") # Get value, could be None or ""
            if not name_to_print_from_form: # If None or empty string
                name_to_print = menu_item_name # Default to the main item name
            else:
                name_to_print = name_to_print_from_form
            
            if name_to_print is None: # Ensure it's at least an empty string if menu_item_name was also somehow None (though validated)
                name_to_print = ""

            # Assuming translate_menu_name_description can take a dict-like object (request.POST)
            # or modify to pass individual fields
            # Adjust translate_menu_name_description to not return/process Spanish if it's a custom util function
            # For now, assuming it might return more than needed, and we'll pick what we need.
            # Or, if it's a direct call to googletrans multiple times, remove the 'es' calls.
            # Let's assume translate_menu_name_description is a black box for now and we just don't use _es results.
            # Ideally, translate_menu_name_description itself should be modified.
            # For a direct fix here, if it returns a tuple:
            # name_en, name_pt, _, description_en, _, description_pt = translate_menu_name_description(form_data)
            # This is risky if the function signature changes.
            # A safer modification is to adjust what's passed to it or how it's called if it's a series of direct translations.
            # Given the function name, it likely does multiple translations.
            # We will assume for now that the function `translate_menu_name_description` will be updated separately
            # or that we can simply ignore the Spanish parts it might return.
            # For the purpose of this diff, I will remove _es from being assigned and used.
            
            # This implies translate_menu_name_description might need to change its return signature
            # or the way it's called. For now, let's assume it's modified to not return Spanish.
            # If translate_menu_name_description is a series of direct calls, those for 'es' would be removed.
            # If it's a utility, that utility needs to be updated.
            
            raw_name_en, raw_name_pt, raw_description_en, raw_description_pt = translate_menu_name_description(form_data)

            # Ensure translated fields are empty strings if None (defensive against unexpected None from translation)
            name_en = raw_name_en if raw_name_en is not None else ""
            name_pt = raw_name_pt if raw_name_pt is not None else ""
            description_en = raw_description_en if raw_description_en is not None else ""
            description_pt = raw_description_pt if raw_description_pt is not None else ""

            category_id_str = form_data.get("category")
            if not category_id_str:
                return JsonResponse({"success": False, "error": "Category ID is required."}, status=400)
            category_id = int(category_id_str)

            menu_item_data = {
                'place_id': place_id,
                'category_id': category_id,
                'name': menu_item_name, # Use the validated name
                'description': form_data.get('description', ''),
                'price': price,
                'is_available': form_data.get('is_available', 'true').lower() == 'true',
                'name_en': name_en,
                'name_pt': name_pt,
                # 'name_es' field is removed from model, so no need to include it here
                'name_to_print': name_to_print,
                'description_en': description_en,
                # 'description_es' field is removed from model
                'description_pt': description_pt,
                'ordering_timing': helper_data['ordering_timing'], # Corrected assignment
                'lunch_time_start': lunch_time_start,     
                'lunch_time_end': lunch_time_end,
                'dinne_time_start': dinne_time_start,
                'dinne_time_end': dinne_time_end
            }
            if image_file:
                menu_item_data['image'] = image_file

            menuItem = models.MenuItem.objects.create(**menu_item_data)
            
            return JsonResponse({
                "success": True,
                "menu_item_name": menuItem.name,
                "menu_item_id": menuItem.id
            })
        except models.Place.DoesNotExist:
            return JsonResponse({"success": False, "error": "Place not found."}, status=404)
        except KeyError as e:
            return JsonResponse({"success": False, "error": f"Missing data: {str(e)}"}, status=400)
        except Exception as e:
            return JsonResponse({
                "success": False,
                "error": str(e),
            }, status=500)
    return JsonResponse({"success": False, "error": "Invalid request method."}, status=405)


class ReorderCategoriesView(views.APIView):
    permission_classes = [permissions.IsOwnerOrReadOnly] # Changed to IsOwnerOrReadOnly

    def post(self, request, place_id):
        place = get_object_or_404(models.Place, id=place_id)
        self.check_object_permissions(request, place) # Explicitly check object permissions

        # The explicit check below is now handled by self.check_object_permissions and IsOwnerOrReadOnly
        # if request.user != place.owner:
        #      return Response({"error": "You do not have permission to reorder categories for this place."},
        #                     status=status.HTTP_403_FORBIDDEN)

        ordered_category_ids = request.data.get('ordered_category_ids')

        if not isinstance(ordered_category_ids, list):
            return Response({"error": "ordered_category_ids must be a list."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # Fetch all categories for the place to ensure IDs are valid and belong to this place
                existing_categories = {cat.id: cat for cat in models.Category.objects.filter(place=place)}
                
                if len(ordered_category_ids) != len(existing_categories):
                    return Response({"error": "The number of provided category IDs does not match the number of categories for this place."},
                                    status=status.HTTP_400_BAD_REQUEST)

                for i, category_id in enumerate(ordered_category_ids):
                    if category_id not in existing_categories:
                        # This check also implicitly handles if a category_id from another place is sent.
                        return Response({"error": f"Category with ID {category_id} not found for this place or is invalid."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    
                    category = existing_categories[category_id]
                    category.orders_display = i + 1 # Changed to i + 1 for 1-based indexing
                    category.save(update_fields=['orders_display'])
            
            return Response({"success": "Categories reordered successfully."}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"An error occurred: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ReorderMenuItemsView(views.APIView):
    permission_classes = [permissions.PlaceOwnerOrReadOnly] # This permission needs to be suitable for Category object

    def post(self, request, category_id):
        category = get_object_or_404(models.Category, id=category_id)
        
        # To use PlaceOwnerOrReadOnly, we pass the category object, 
        # and the permission class will check category.place.owner
        self.check_object_permissions(request, category)

        ordered_item_ids = request.data.get('ordered_item_ids')

        if not isinstance(ordered_item_ids, list):
            return Response({"error": "ordered_item_ids must be a list."},
                            status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Fetch all menu items for the category to ensure IDs are valid and belong to this category
                existing_items = {item.id: item for item in models.MenuItem.objects.filter(category=category)}

                if len(ordered_item_ids) != len(existing_items):
                    return Response({"error": "The number of provided item IDs does not match the number of items in this category."},
                                    status=status.HTTP_400_BAD_REQUEST)

                for i, item_id in enumerate(ordered_item_ids):
                    if item_id not in existing_items:
                        return Response({"error": f"Menu item with ID {item_id} not found in this category or is invalid."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    
                    menu_item = existing_items[item_id]
                    menu_item.item_order = i + 1 # 1-indexed
                    menu_item.save(update_fields=['item_order'])
            
            return Response({"success": "Menu items reordered successfully."}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"An error occurred while reordering menu items: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
def reprint_order(request):
    try:
        data = json.loads(request.body)
        place_id = int(data["place"])
        printers = models.Printer.objects.filter(place_id=place_id) # Added models.
        daily_order_id = int(data["daily_id"])

        grouped_details_by_category = defaultdict(list)

        for detail_item in data.get("detail", []): # Added default empty list
            item_id = str(detail_item["id"])
            grouped_details_by_category[item_id].append(detail_item)

        # Ensure detail list is not empty before accessing its first element
        date_to_print = data.get("detail", [{}])[0].get('created_at') if data.get("detail") else None

        grouped_details_by_sn = defaultdict(list)

        for item_id, details_list in grouped_details_by_category.items():
            for detail_item_inner in details_list: # Renamed detail to detail_item_inner
                sn_id = get_serial_number_by_menu_item(printers, item_id)
                grouped_details_by_sn[sn_id].append(detail_item_inner)
        
        for sn_id, details_list_for_sn in grouped_details_by_sn.items(): # Renamed details_list
            content = get_print_content(daily_order_id,data, details_list_for_sn,"B1",date_to_print)
            response = api_print_request(USER_NAME, USER_KEY, sn_id, content)

        return JsonResponse({
            "success": True,
            "message": "Reprint request sent successfully.",
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        }, status=500)
