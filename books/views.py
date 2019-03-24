import os
from django.contrib import messages, admin
from django.db.models import Count
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404

from django.utils import timezone
from django.utils.http import urlencode
from django.views.generic.base import View, TemplateView
from filters.mixins import (
    FiltersMixin,
)
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from books.google import BookFinder
from books.serializers import *
from .forms import IsbnForm
from .models import Book as BookModel


class FrontendView(TemplateView):
    template_name = 'index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['analyticsAccountId'] = os.environ.get('ANALYTICS_ACCOUNT_ID')
        return context

class IsbnFormView(View):
    def get(self, request):
        form = IsbnForm()

        return render(request, 'isbn.html', {
            'form': form,
            'site_header': admin.site.site_header,
            'books_isbn_url': reverse('admin:books_book_isbn')
        })

    def post(self, request):
        form = IsbnForm(request.POST)
        if form.is_valid():
            isbn = form.cleaned_data["isbn"]
            book_from_db = BookModel.objects.filter(isbn=isbn).distinct()
            book = BookFinder.fetch(isbn)

            if book_from_db:
                 messages.warning(request, 'The requested book is on the table.')
                 return self.get(request)

            if book == {}:
                messages.warning(request, 'Sorry! We could not find the book with the ISBN provided.')
            else:
                messages.info(request, "Found! Go ahead, modify book template and save.")

            return redirect('{}?{}'.format(reverse('admin:books_book_add'), urlencode(book)))
        else:
            messages.error(request, 'Invalid ISBN provided!')

            return self.get(request)


def get_book_filters_from_request(request, filters=('book_title', 'book_author')):
    """Get book filters from a request
    Given a request, return all filters with __icontains
    Example:
        > filters=('book_title') returns {title__icontains} if request has a book_title attribute
    """
    query = Q()

    query_params = {query_param.strip(): request.query_params.get(query_param).strip() for query_param in request.query_params}

    query_filters = {filter[5:] + "__icontains": query_params.get(filter) for filter in filters if
            filter in query_params}

    for key in query_filters:
        query.add(Q(**{key: query_filters[key]}), Q.OR)

    return query


class LibraryViewSet(FiltersMixin, viewsets.ModelViewSet):
    queryset = Library.objects.all()
    serializer_class = LibraryCompactSerializer
    lookup_field = 'slug'
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ('id', 'name')
    ordering = ('id',)  # default ordering

    # add a mapping of query_params to db_columns(queries)
    filter_mappings = {
        'id': 'id',
        'name': 'name__icontains',
        'slug': 'slug__icontains'
    }


class BookViewSet(FiltersMixin, viewsets.ModelViewSet):
    serializer_class = BookSerializer
    queryset = Book.objects.filter()

    def list(self, request, library_slug=None):
        self.pagination_class.size = 1
        self.filter_backends = ()
        self.ordering_fields = ()
        self.ordering = ()

        library = Library.objects.get(slug=library_slug)

        book_filters = get_book_filters_from_request(request, ('book_title', 'book_author'))
        book_filters.add(Q(bookcopy__library__slug__exact=library_slug), Q.AND)

        books = self.queryset.filter(book_filters).order_by('title')
        books = books.annotate(copies=Count('id'))

        page = self.paginate_queryset(books)

        serializer = BookSerializer(page, many=True, context={
            'request': request,
            'library': library,
            'user': request.user,
        })

        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=['post'])
    def borrow(self, request, library_slug=None, pk=None):
        book = get_object_or_404(self.queryset, pk=pk)
        library = Library.objects.get(slug=library_slug)
        try:
            book.borrow(user=request.user, library=library)
            return Response({
                'action': book.available_action(
                    library=library,
                    user=request.user,
                )
            })
        except ValueError as error:
            return Response({'message': str(error)}, status=400)

    @action(detail=True, methods=['post'], url_path='return')
    def returnToLibrary(self, request, library_slug=None, pk=None):
        book = get_object_or_404(self.queryset, pk=pk)
        library = Library.objects.get(slug=library_slug)
        try:
            book.returnToLibrary(user=request.user, library=library)
            return Response({
                'action': book.available_action(
                    library=library,
                    user=request.user,
                )
            })
        except ValueError as error:
            return Response({'message': str(error)}, status=400)


class BookCopyViewSet(viewsets.ModelViewSet):
    queryset = BookCopy.objects.all()
    serializer_class = BookCopySerializer


class BookCopyBorrowView(APIView):
    def post(self, request, id=None):
        try:
            book_copy = BookCopy.objects.get(pk=id)
            book_copy.user = request.user
            book_copy.borrow_date = timezone.now()
            book_copy.save()
        except BookCopy.DoesNotExist:
            raise Http404("Book Copy not found")
        return Response({
            'status': 'Book borrowed',
            'action': book_copy.book.available_action(
                library=book_copy.library,
                user=request.user,
            )
        })


class BookCopyReturnView(APIView):
    def post(self, request, id=None):
        try:
            book_copy = BookCopy.objects.get(pk=id)
            book_copy.user = None
            book_copy.borrow_date = None
            book_copy.save()
        except:
            raise Http404("Book Copy not found")
        return Response({
            'status': 'Book returned',
            'action': book_copy.book.available_action(
                library=book_copy.library,
                user=request.user,
            )
        })


class UserView(APIView):
    def get(self, request, format=None):
        return Response({
            'user': UserSerializer(request.user).data,
        })

class UserBooksView(APIView):
    def get(self, request, format=None):
        books = Book.objects.filter(bookcopy__user=request.user)
        return Response({
            'results': BookSerializer(books, many=True, context={'user': request.user}).data
        })
