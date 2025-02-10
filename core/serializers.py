from rest_framework import serializers
from . import models

class MenuItemSerializer(serializers.ModelSerializer):
  class Meta:
    model = models.MenuItem
    fields = "__all__"

class CategorySerializer(serializers.ModelSerializer):
  menu_items = MenuItemSerializer(many=True, read_only=True)

  class Meta:
    model = models.Category
    fields = (
      'id', 
      'name', 
      'menu_items', 
      'place',
      'name_en',
      'name_pt',
      'name_es',
      'orders_display'
    )

class PrinterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Printer
        fields = "__all__"
        #fields = ('id', 'serial_number', 'place','category_name','category','printer_status','printer_status_info')

class TableSerializer(serializers.ModelSerializer):
  class Meta:
    model = models.Table
    fields = ('id', 'place', 'table_number', 'last_ordering_time', 'number_people', 'created_at', 'blocked')

class PlaceDetailSerializer(serializers.ModelSerializer):
  categories = CategorySerializer(many=True, read_only=True)
  printers = PrinterSerializer(many=True)
  tables = TableSerializer(many=True)
  class Meta:
    model = models.Place
    fields = (
      'id',
      'name', 
      'image', 
      'number_of_tables', 
      'categories',
      'printers',
      'place_type',
      'ordering_limit_interval',
      "tables",
      'lunch_time_start',
      'lunch_time_end',
      'dinne_time_start',
      'dinne_time_end'
    )

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

class OrderSerializer(serializers.ModelSerializer):
  class Meta:
    model = models.Order
    fields = "__all__"
