from django.db import models
from django.utils import timezone
from django.conf import settings

class Place(models.Model):

  buffet = 'buffet'
  normal = 'normal'

  PLACE_TYPES = [
      (buffet, 'Bubble Tea'),
      (normal, 'Restaurant'),
  ]

  owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
  name = models.TextField(max_length=500)
  image = models.ImageField(upload_to='place_images/', blank=True, null=True)
  number_of_tables = models.IntegerField(default=1)
  font = models.TextField(max_length=500, blank=True)
  color = models.TextField(max_length=500, blank=True)
  languages = models.TextField(blank=True,null=True)
  dotsColor = models.TextField(max_length=500,default='#4267b2',blank=True,null=True)
  cornersDotColor = models.TextField(max_length=500,default='#4267b2',blank=True,null=True)
  cornersSquareColor = models.TextField(max_length=500,default='#4267b2',blank=True,null=True)
  backgroundColorleft = models.TextField(max_length=500,default='white',blank=True,null=True)
  backgroundColorright = models.TextField(max_length=500,default='#25008E8',blank=True,null=True)
  place_type = models.TextField(max_length=500, default=normal,choices=PLACE_TYPES)
  ordering_limit_interval = models.IntegerField(default=300,null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  lunch_time_start = models.IntegerField(null=True, blank=True)
  lunch_time_end = models.IntegerField(null=True, blank=True)
  dinne_time_start = models.IntegerField(null=True, blank=True)
  dinne_time_end = models.IntegerField(null=True, blank=True)

  def __str__(self):
    return "{}/{}".format(self.owner.user_name, self.name)
  
  def save(self, *args, **kwargs):
          created = not self.pk  # Check if the instance is being created or updated
          super().save(*args, **kwargs)
          if created:
              # Create tables if the place is new
              for table_number in range(1, self.number_of_tables + 1):
                  Table.objects.create(place=self, table_number=table_number)
          else:
              # Retrieve existing tables
              existing_table_numbers = set(Table.objects.filter(place=self).values_list('table_number', flat=True))

              if self.number_of_tables > len(existing_table_numbers):
                  # Create new tables for additional table numbers
                  new_table_numbers = set(range(1, self.number_of_tables + 1)) - existing_table_numbers
                  for table_number in new_table_numbers:
                      Table.objects.create(place=self, table_number=table_number)
              elif self.number_of_tables < len(existing_table_numbers):
                  # Delete excess tables
                  excess_table_numbers = existing_table_numbers - set(range(1, self.number_of_tables + 1))
                  Table.objects.filter(place=self, number__in=excess_table_numbers).delete()

class Table(models.Model):
  place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='tables')
  table_number = models.IntegerField()
  last_ordering_time = models.IntegerField(null=True, blank=True)
  number_people = models.IntegerField(null=True,blank=True,default=0)
  created_at = models.DateTimeField(auto_now_add=True)
  blocked = models.BooleanField(default=True)

  def __str__(self):
    return f"Table {self.table_number} at {self.place.name}"

class Printer(models.Model):
  serial_number = models.TextField(max_length=500)
  place = models.ForeignKey(Place, on_delete=models.CASCADE,related_name='printers')
  category_name = models.TextField(max_length=500,default=None,blank=True, null=True)
  category = models.TextField(max_length=500,default=None,blank=True, null=True)
  menu_item_id = models.TextField(max_length=500,default=None,blank=True, null=True)
  printer_status = models.TextField(max_length=500,blank=True, null=True)
  printer_status_info = models.TextField(max_length=500,blank=True, null=True)
  created_at = models.DateTimeField(auto_now_add=True)
  

class Category(models.Model):
  place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="categories")
  name = models.TextField(max_length=500) # Default/Chinese name
  name_en = models.TextField(max_length=500,blank=True, null=True) # English name
  name_pt = models.TextField(max_length=500,blank=True, null=True) # Portuguese name
  created_at = models.DateTimeField(auto_now_add=True)
  orders_display = models.IntegerField(blank=True,null=True)
  def __str__(self):
    return "{}/{}".format(self.place, self.name)
  
class MenuItem(models.Model):

  lunch = 'lunch'
  dinner = 'dinner'
  lunch_and_dinner = 'lunch_and_dinner'

  ORDERING_TIMING = [
      (lunch, 'lunch'),
      (dinner, 'dinner'),
      (lunch_and_dinner, 'lunch_and_dinner')
  ]

  place = models.ForeignKey(Place, on_delete=models.CASCADE)
  category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="menu_items")
  name = models.TextField(max_length=500)
  price = models.FloatField(default=0)
  image = models.ImageField(upload_to='menu_item_images/', blank=True, null=True)
  is_available = models.BooleanField(default=True)
  name_en = models.TextField(max_length=500,blank=True, null=True) # English name
  name_pt = models.TextField(max_length=500,blank=True, null=True) # Portuguese name
  name_to_print = models.TextField(max_length=500,blank=True, null=True)
  description = models.TextField(blank=True, null=True) # Default/Chinese description
  description_en = models.TextField(blank=True, null=True) # English description
  description_pt = models.TextField(blank=True, null=True) # Portuguese description
  created_at = models.DateTimeField(auto_now_add=True)
  ordering_timing = models.TextField(max_length=500, default=lunch_and_dinner,choices=ORDERING_TIMING)
  lunch_time_start = models.IntegerField(null=True, blank=True)
  lunch_time_end = models.IntegerField(null=True, blank=True)
  dinne_time_start = models.IntegerField(null=True, blank=True)
  dinne_time_end = models.IntegerField(null=True, blank=True)
  code = models.TextField(max_length=20,blank=True, null=True)
  item_order = models.IntegerField(null=True, blank=True) # Field for ordering within category

  def __str__(self):
    return "{}/{}".format(self.category, self.name)

class Order(models.Model):
  PROCESSING_STATUS = "processing"
  COMPLETED_STATUS = "completed"
  STATUSES = (
    (PROCESSING_STATUS, 'Processing'),
    (COMPLETED_STATUS, 'Completed'),
  )

  place = models.ForeignKey(Place, on_delete=models.CASCADE)
  table = models.TextField(max_length=10)
  detail = models.TextField()
  amount = models.IntegerField()
  status = models.TextField(max_length=500, choices=STATUSES, default=PROCESSING_STATUS)
  created_at = models.DateTimeField(auto_now_add=True)
  isPrinted = models.BooleanField(default=False)
  isTakeAway = models.BooleanField(default=False) 
  phoneNumer = models.IntegerField(blank=True, null=True)
  comment = models.TextField(max_length=5000,blank=True, null=True)
  arrival_time = models.TimeField(null=True, blank=True)
  customer_name = models.TextField(max_length=500,blank=True, null=True,default=None)
  daily_id = models.IntegerField(default=0)
  sn_id = models.TextField(max_length=50,blank=True, null=True)
  
  def __str__(self):
    return "{}/{}/${}".format(self.place, self.table, self.amount)

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT) # PROTECT ensures a MenuItem isn't deleted if it's part of an order.
    quantity = models.IntegerField()
    price_at_time_of_order = models.FloatField() # Price of one unit of the item
    category_name_at_time_of_order = models.CharField(max_length=500, blank=True, null=True) # Captures the category name (Chinese, as discussed) at time of order.
    created_at = models.DateTimeField(auto_now_add=True) # For consistency

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name} (Order ID: {self.order.id})"

    @property
    def total_item_price(self):
        # Calculates total for this line item (quantity * price_at_time_of_order)
        return self.quantity * self.price_at_time_of_order
