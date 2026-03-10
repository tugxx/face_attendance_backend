from rest_framework import serializers

from custom_account.domains.user_domain import UserDomain
from custom_account.models import UserModel, Profile, BiometricCredential



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
    

class UserSerializer(serializers.ModelSerializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15, required=False)
    created_on = serializers.DateTimeField(read_only=True)
    # 🚨 notice: we don’t expose password in API responses

    class Meta:
        model = UserModel
        fields = [
            "id", "username", "email", "is_active",
            "phone", "created_on", "role"
        ]
        read_only_fields = ["id", "created_on"]

    def get_fields(self):
        """Dynamically make some fields read-only depending on the user."""
        fields = super().get_fields()

        request = self.context.get("request", None)
        if request and not request.user.is_staff:  # Non-admin user
            # Make restricted fields read-only
            fields["role"].read_only = True
            fields["is_active"].read_only = True

        return fields
    
    def to_domain(self) -> UserDomain:
        """Convert serializer data -> UserDomain."""
        return UserDomain.from_dict(self.validated_data)

    @staticmethod
    def from_domain(domain: UserDomain) -> dict:
        """Convert UserDomain -> dict (API response)."""
        return domain.to_dict()
    
    def to_representation(self, instance):
        # Nếu instance là UserDomain, convert sang dict
        if isinstance(instance, UserDomain):
            return {
                'id': instance.id,
                'username': instance.username,
                'email': instance.email,
                'role': instance.role,
                'created_on': instance.created_on,
                'phone': instance.phone,
            }
        return super().to_representation(instance)
    

class CookieOnlyJWTSerializer(serializers.Serializer):
    """
    Serializer này cố tình không khai báo trường 'access' và 'refresh'.
    Khi dj_rest_auth ném data vào đây, nó sẽ tự động lọc bỏ 2 token đó, 
    chỉ giữ lại cục 'user' để in ra màn hình.
    """
    user = UserSerializer(read_only=True)

# ----------------------------------------------------
#   SYNC DATA 
# ----------------------------------------------------

class BiometricSyncSerializer(serializers.ModelSerializer):
    class Meta:
        model = BiometricCredential
        # Chỉ lấy những trường cần thiết cho việc nhận diện offline
        fields = ['rfid_card_id', 'face_vector_1', 'face_vector_2', 'is_active', 'updated_at']


class ProfileSyncSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['display_name', 'avatar_id', 'dob', 'gender', 'updated_at']


class UserSyncSerializer(serializers.ModelSerializer):
    # Lấy data từ bảng OneToOne
    profile = ProfileSyncSerializer(read_only=True)
    biometric = BiometricSyncSerializer(read_only=True)

    class Meta:
        model = UserModel
        fields = [
            'id', 'username', 'email', 'role', 'phone', 
            'is_active', 'created_on', 'updated_on', 
            'profile', 'biometric'
        ]