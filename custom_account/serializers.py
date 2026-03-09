from rest_framework import serializers

from custom_account.domains.user_domain import UserDomain

class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    # UPDATE: Thêm các role của hệ thống quản lý trường học
    role = serializers.ChoiceField(
        choices=["student", "teacher", "parent", "driver", "admin"], 
        default="student"
    )
    phone = serializers.CharField(max_length=15, required=False)

    def to_domain(self):
        """Convert validated data into a UserDomain object"""
        # Giả định bạn đã import UserDomain
        return UserDomain(**self.validated_data)