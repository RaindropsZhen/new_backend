from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import User

class UserRegistrationSerializer(serializers.ModelSerializer):
    password_confirmation = serializers.CharField(style={'input_type': 'password'}, write_only=True)

    class Meta:
        model = User
        fields = ['id','email', 'user_name', 'phone_number', 'password', 'password_confirmation']
        extra_kwargs = {
            'password': {'write_only': True, 'style': {'input_type': 'password'}}
        }

    def validate(self, data):
        # Check if the two password fields match
        if data['password'] != data['password_confirmation']:
            raise serializers.ValidationError({"password": "密码不一致"})

        # Validate the password with Django's built-in validators
        validate_password(data['password'])

        return data

    def create(self, validated_data):
        # Remove the password_confirmation field before saving
        validated_data.pop('password_confirmation', None)
        user = User.objects.create_user(**validated_data)
        return user
