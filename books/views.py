from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.response import Response
from books.serializers import *
from books.models import *


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer

class LibraryViewSet(viewsets.ModelViewSet):
    queryset = Library.objects.all()
    serializer_class = LibraryCompactSerializer
    lookup_field = 'slug'

    def retrieve(self, request, slug=None):
        library = Library.objects.get(slug=slug)
        serializer = LibrarySerializer(library, context={ 'request': request })
        return Response(serializer.data)