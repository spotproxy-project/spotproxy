from rest_framework import serializers
from assignments.models import Proxy


class ProxySerializer(serializers.ModelSerializer):
    class Meta:
        model = Proxy
        fields = ("url", "ip")

    def create(self, validated_data):
        proxy = super().create(validated_data)
        return proxy


# class ProxyUpdateSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Proxy
#         fields = (
#             "ip",

#         )

#     def create(self, validated_data):
#         proxy = super().create(validated_data)
#         return proxy
