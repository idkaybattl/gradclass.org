from django.http import HttpResponse
from django.template import loader


def abi(request):
    template = loader.get_template('index.html')
    return HttpResponse(template.render())

def calendar(request):
    template = loader.get_template('calendar.html')
    return HttpResponse(template.render())
