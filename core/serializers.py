from rest_framework import serializers
from . import models

class MenuItemSerializer(serializers.ModelSerializer):
  class Meta:
    model = models.MenuItem
    fields = "__all__"

class CategorySerializer(serializers.ModelSerializer):
  menu_items = serializers.SerializerMethodField() # Changed for custom sorting

  class Meta:
    model = models.Category
    fields = (
      'id', 
      'name', 
      'menu_items', 
      'place',
      'name_en',
      'name_pt',
      'orders_display'
    )
  
  def get_menu_items(self, instance):
    # Fetch menu items related to the category instance, ordered by 'item_order'.
    # 'created_at' can be a secondary sort key for items with no order or same order.
    menu_items_queryset = instance.menu_items.all().order_by('item_order', 'created_at')
    return MenuItemSerializer(menu_items_queryset, many=True, context=self.context).data

class PrinterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Printer
        fields = "__all__"

class TableSerializer(serializers.ModelSerializer):
  class Meta:
    model = models.Table
    fields = ('id', 'place', 'table_number', 'last_ordering_time', 'number_people', 'created_at', 'blocked')

class PlaceDetailSerializer(serializers.ModelSerializer):
  categories = serializers.SerializerMethodField() # Updated for custom sorting
  printers = PrinterSerializer(many=True)
  tables = TableSerializer(many=True)
  class Meta:
    model = models.Place
    fields = (
      'id',
      'name', 
      'image', 
      'number_of_tables', 
      'categories', # Will use the SerializerMethodField
      'printers',
      'place_type',
      'ordering_limit_interval',
      "tables",
      'lunch_time_start',
      'lunch_time_end',
      'dinne_time_start',
      'dinne_time_end'
    )

  def get_categories(self, instance):
    # Fetch categories related to the place instance,
    # ordered by 'orders_display' (ascending, nulls typically first or last depending on DB).
    # 'created_at' is a secondary sort key for consistent ordering among items with same 'orders_display' or null.
    # Using .order_by('orders_display', 'created_at') ensures that nulls in orders_display are handled consistently
    # (usually appearing first in PostgreSQL, last in MySQL/SQLite unless explicitly handled with .asc(nulls_first=True) or similar,
    # but Django's ORM tries to provide a consistent behavior).
    # If orders_display can be null and a specific nulls ordering is needed, more complex expressions might be required
    # e.g. from django.db.models.functions import Coalesce, Value
    # .order_by(Coalesce('orders_display', Value(999999)), 'created_at') # to put nulls last
    categories_queryset = instance.categories.all().order_by('orders_display', 'created_at')
    # Pass the current serializer context, which might be needed by CategorySerializer if it uses context-dependent fields
    return CategorySerializer(categories_queryset, many=True, context=self.context).data

class PlaceSerializer(serializers.ModelSerializer):
  class Meta:
    model = models.Place
    fields = (
        'id',
        'name', 
        'image',
        'number_of_tables',
        'place_type',
        'ordering_limit_interval',
        'lunch_time_start',
        'lunch_time_end',
        'dinne_time_start',
        'dinne_time_end'
      )

# Serializer for the OrderItem model
class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)
    # You can add more fields from MenuItem if needed, e.g., menu_item_code = serializers.CharField(source='menu_item.code', read_only=True)
    
    class Meta:
        model = models.OrderItem
        fields = (
            'id', 
            'menu_item', 
            'menu_item_name', 
            'quantity', 
            'price_at_time_of_order', 
            'category_name_at_time_of_order',
            'total_item_price' # This is a @property in the model
        )
        read_only_fields = ('total_item_price',)

class OrderSerializer(serializers.ModelSerializer):
  items = OrderItemSerializer(many=True, read_only=True)
  place_name = serializers.CharField(source='place.name', read_only=True)

  class Meta:
    model = models.Order
    fields = (
        'id', 
        'place', 
        'place_name', 
        'table', 
        'detail', # Stores JSON summary of items
        'amount', # Total order amount
        'status', 
        'created_at', 
        'isPrinted', 
        'isTakeAway', 
        'phoneNumer', 
        'comment', 
        'arrival_time', 
        'customer_name', 
        'daily_id', 
        'sn_id', # Main sn_id for the order (e.g., first item's printer)
        'items' # Nested list of order items
    )
    read_only_fields = ('created_at', 'daily_id', 'items', 'place_name')
