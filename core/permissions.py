from rest_framework import permissions

from . import models


class IsOwnerOrReadOnly(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the place.
        return obj.owner == request.user


class PlaceOwnerOrReadOnly(permissions.BasePermission):

    def has_permission(self, request, view):
        # Allow GET, HEAD, OPTIONS requests for any user (authenticated or not for
        # public APIs, or rely on IsAuthenticated if that's a global default or
        # added to views).
        if request.method in permissions.SAFE_METHODS:
            return True
        # For unsafe methods (POST, PUT, PATCH, DELETE), user must be authenticated.
        # The actual ownership check will happen in has_object_permission.
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner.
        # Check if the object itself is a Place instance.
        if isinstance(obj, models.Place):
            return obj.owner == request.user
        # Check if the object has a 'place' attribute, and that place has an 'owner'.
        elif hasattr(obj, "place") and hasattr(obj.place, "owner"):
            return obj.place.owner == request.user
        # Fallback or if object structure is different, deny permission.
        return False
