from django.urls import path
from assignments import views

app_name = "assignments"
urlpatterns = [
    path("getnew", views.AssignmentView.as_view(), name="assignment"),
    path("postupdate", views.ProxyUpdateView.as_view(), name="postupdate"),
    path("postsingleupdate", views.RealProxyUpdateView.as_view(), name="postsingleupdate"),
    path("getid", views.IDAssignmentView.as_view(), name="getid"),
    path("postavgclient", views.ClientAvgPostView.as_view(), name="postavgclient"),
    path("postavgproxy", views.ProxyAvgPostView.as_view(), name="postavgproxy"),
]
