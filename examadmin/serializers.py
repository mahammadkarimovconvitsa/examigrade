from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import *

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'name', 'role']

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    
    def validate(self, data):
        username = data.get('username')
        password = data.get('password')
        
        if username and password:
            user = authenticate(username=username, password=password)
            if user:
                if user.is_active:
                    data['user'] = user
                else:
                    raise serializers.ValidationError('User account is disabled.')
            else:
                raise serializers.ValidationError('Invalid credentials.')
        else:
            raise serializers.ValidationError('Must include username and password.')
        
        return data

class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'name', 'logo', 'is_active', 'created_at', 'updated_at']

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name','is_foreign_language', 'is_active', 'created_at', 'updated_at']

class ClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = Class
        fields = ['id', 'name', 'is_active', 'created_at', 'updated_at']

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name', 'is_active', 'created_at', 'updated_at']

class SpecializationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialization
        fields = ['id', 'name', 'code', 'is_active', 'created_at', 'updated_at']

class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'name', 'is_active', 'created_at', 'updated_at']

class ExamSubjectSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    
    class Meta:
        model = ExamSubject
        fields = ['subject', 'subject_name', 'question_count']

class SectionDetailSerializer(serializers.ModelSerializer):
    section_name = serializers.CharField(source='section.name', read_only=True)
    subjects = ExamSubjectSerializer(source='exam_subjects', many=True)
    subject_count = serializers.ReadOnlyField()
    group_name = serializers.CharField(allow_null=True, required=False)
    specialization_code = serializers.CharField(source='specialization.code', read_only=True, default=None)
    specialization_name = serializers.CharField(source='specialization.name', read_only=True, default=None)
    class Meta:
        model = SectionDetail
        fields = ['section', 'section_name', 'variant_count', 'subject_count', 'subjects','group','group_name',
                  'specialization', 'specialization_code', 'specialization_name']

class ExamCreateSerializer(serializers.ModelSerializer):
    branch_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True,required=False)
    groups = serializers.ListField(child=serializers.CharField(), required=False, write_only=True, allow_null=True)
    class_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    section_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True)
    section_details = SectionDetailSerializer(many=True, write_only=True)
    specialization_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    
    class Meta:
        model = Exam
        fields = ['name', 'date', 'type', 'branch_ids', 'class_ids', 'section_ids', 'groups', 'section_details', 'specialization_ids']
    
    def create(self, validated_data):
        
        class_ids = validated_data.pop('class_ids', [])
        section_ids = validated_data.pop('section_ids')
        groups = validated_data.pop('groups', [])
        section_details_data = validated_data.pop('section_details')
        specialization_ids = validated_data.pop('specialization_ids', [])
        branch_ids = Branch.objects.all().values_list('id', flat=True)
        
        exam = Exam.objects.create(**validated_data)
        
        # Set relationships
        exam.branches.set(branch_ids)
        if class_ids:
            exam.classes.set(class_ids)
        exam.sections.set(section_ids)
        group_ids = []
        for g in groups:
            gro = Group.objects.get(name=g)
            group_ids.append(gro.id)
        exam.groups.set(group_ids)
        if specialization_ids:
            exam.specializations.set(specialization_ids)
        
        # Create section details
        for section_detail_data in section_details_data:
            group_name = section_detail_data.get('group_name')
            specialization = section_detail_data.get('specialization')

            if group_name:
                group = Group.objects.get(name=group_name)
                section_detail = SectionDetail.objects.create(
                    exam=exam,
                    section=section_detail_data['section'],
                    variant_count=section_detail_data['variant_count'],
                    group=group,
                    group_name=group_name
                )
            elif specialization:
                section_detail = SectionDetail.objects.create(
                    exam=exam,
                    section=section_detail_data['section'],
                    variant_count=section_detail_data['variant_count'],
                    specialization=specialization
                )
            else:
                section_detail = SectionDetail.objects.create(
                    exam=exam,
                    section=section_detail_data['section'],
                    variant_count=section_detail_data['variant_count']
                )

            subjects_data = section_detail_data.pop('exam_subjects')
            for subject_data in subjects_data:
                ExamSubject.objects.create(
                    section_detail=section_detail,
                    subject=subject_data['subject'],
                    question_count=subject_data['question_count']
                )
        
        return exam
    

class ExamUpdateSerializer(serializers.ModelSerializer):
        branch_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
        class_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
        section_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
        groups = serializers.ListField(child=serializers.CharField(), required=False, write_only=True, allow_null=True)
        section_details = SectionDetailSerializer(many=True, required=False)
        specialization_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)

        class Meta:
            model = Exam
            fields = ['name', 'date', 'type', 'branch_ids', 'class_ids', 'section_ids', 'groups', 'section_details', 'specialization_ids']

        def update(self, instance, validated_data):
            # Update branches
            if validated_data.get('branch_ids'):
                branch_ids = validated_data.pop('branch_ids')
                instance.branches.set(branch_ids)

            # Update classes
            if validated_data.get('class_ids'):
                class_ids = validated_data.pop('class_ids')
                instance.classes.set(class_ids)

            # Update sections
            if validated_data.get('section_ids'):
                section_ids = validated_data.pop('section_ids')
                instance.sections.set(section_ids)

            branches = Branch.objects.all().values_list('id', flat=True)
            instance.branches.set(branches)
            # Update groups
            if 'groups' in validated_data:
                groups = validated_data.pop('groups')
                instance.groups.set(groups)

            # Update specializations
            if 'specialization_ids' in validated_data:
                specialization_ids = validated_data.pop('specialization_ids')
                instance.specializations.set(specialization_ids)

            # Update section details
            if 'section_details' in validated_data:
                section_details_data = validated_data.pop('section_details')
                instance.section_details.all().delete()
                for section_detail_data in section_details_data:
                    group_name = section_detail_data.get('group_name')
                    specialization = section_detail_data.get('specialization')

                    if group_name:
                        group = Group.objects.get(name=group_name)
                    else:
                        group = None

                    subjects_data = section_detail_data.pop('exam_subjects', [])
                    section_detail = SectionDetail.objects.create(
                        exam=instance,
                        section=section_detail_data['section'],
                        variant_count=section_detail_data['variant_count'],
                        group=group,
                        group_name=group_name,
                        specialization=specialization
                    )
                    for subject_data in subjects_data:
                        ExamSubject.objects.create(
                            section_detail=section_detail,
                            subject=subject_data['subject'],
                            question_count=subject_data['question_count']
                        )

            # Update other fields
            for attr, value in validated_data.items():
                setattr(instance, attr, value)

            instance.save()
            return instance

class ExamListSerializer(serializers.ModelSerializer):
    branch_count = serializers.ReadOnlyField()
    branch_ids = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Exam
        fields = ['id', 'name', 'date', 'type', 'participant_count', 'branch_count', 'is_active', 'branch_ids']

    def get_branch_ids(self, obj):
        return list(obj.branches.values_list('id', flat=True))
    def get_participant_count(self, obj):
        return obj.student_results.count()

class ExamDetailSerializer(serializers.ModelSerializer):
    branches = BranchSerializer(many=True, required=False)
    classes = ClassSerializer(many=True, required=False)
    sections = SectionSerializer(many=True, required=False)
    section_details = SectionDetailSerializer(many=True, required=False)
    specializations = SpecializationSerializer(many=True, required=False)
    branch_count = serializers.ReadOnlyField()
    branch_ids = serializers.SerializerMethodField()
    class_ids = serializers.SerializerMethodField()
    section_ids = serializers.SerializerMethodField()
    group_ids = serializers.SerializerMethodField()
    specialization_ids = serializers.SerializerMethodField()
    
    def update(self, instance, validated_data):
        # Update branches
        if validated_data.get('branch_ids'):
            branch_data = validated_data.pop('branch_ids')
            instance.branches.set(branch_data)

        # Update classes
        if validated_data.get('class_ids'):
            class_data = validated_data.pop('class_ids')
            instance.classes.set(class_data)

        # Update sections
        if validated_data.get('section_ids'):
            section_data = validated_data.pop('section_ids')
            instance.sections.set(section_data)

        # Update section details
        if 'section_details' in validated_data:
            section_details_data = validated_data.pop('section_details')
            instance.section_details.all().delete()  # Clear existing section details
            for section_detail_data in section_details_data:
                subjects_data = section_detail_data.pop('exam_subjects', [])
                section_detail = SectionDetail.objects.create(
                    exam=instance,
                    section=section_detail_data['section'],
                    variant_count=section_detail_data['variant_count']
                )
                for subject_data in subjects_data:
                    ExamSubject.objects.create(
                        section_detail=section_detail,
                        subject=subject_data['subject'],
                        question_count=subject_data['question_count']
                    )

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

    class Meta:
        model = Exam
        fields = ['id', 'name', 'date', 'type', 'participant_count', 'branch_count', 'is_active', 
                 'branches', 'classes', 'sections', 'section_details', 'groups', 'specializations',
                 'branch_ids', 'class_ids', 'section_ids', 'created_at', 'updated_at','group_ids', 'specialization_ids']
    
    def get_branch_ids(self, obj):
        return list(obj.branches.values_list('id', flat=True))
    
    def get_class_ids(self, obj):
        return list(obj.classes.values_list('id', flat=True))
    
    def get_section_ids(self, obj):
        return list(obj.sections.values_list('id', flat=True))
    def get_group_ids(self, obj):
        return obj.groups.values()
    def get_specialization_ids(self, obj):
        return list(obj.specializations.values_list('id', flat=True))

class StudentResultSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    specialization_name = serializers.CharField(source='specialization.name', read_only=True, default=None)
    
    class Meta:
        model = StudentResult
        fields = ['id', 'student_name', 'work_number', 'gender', 'contact_number', 'school_number',
                 'branch', 'branch_name', 'variant', 'section', 'section_name', 'class_level','group',
                 'specialization', 'specialization_name',
                 'total_score', 'answer_card_pdf','is_active']

class SubjectResultSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False)
    
    class Meta:
        model = SubjectResult
        fields = ['subject', 'subject_name', 'total_questions', 'correct_answers', 'wrong_answers', 
                 'empty_answers', 'score', 'percentage', 'subject_data']
    
    def to_internal_value(self, data):
        """
        Handle both subject ID and subject object
        """
        if isinstance(data.get('subject'), Subject):
            # If subject is already a Subject instance, convert to ID
            data = data.copy()
            data['subject'] = data['subject'].id
        return super().to_internal_value(data)

class DetailedStudentResultSerializer(serializers.ModelSerializer):
    exam = ExamDetailSerializer(read_only=True)
    branch = BranchSerializer(read_only=True)
    section = serializers.PrimaryKeyRelatedField(queryset=Section.objects.all(), required=False)
    group = GroupSerializer(read_only=True)
    group_id = serializers.IntegerField(required=False, write_only=True)
    specialization = SpecializationSerializer(read_only=True)
    specialization_id = serializers.IntegerField(required=False, write_only=True)
    subject_results = SubjectResultSerializer(many=True, read_only=False)
    overall_stats = serializers.SerializerMethodField()
    section_name = serializers.SerializerMethodField()




    def get_section_name(self, obj):
        return obj.section.name if obj.section else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['group_id'] = instance.group.id if instance.group else None
        data['specialization_id'] = instance.specialization.id if instance.specialization else None
        return data

    class Meta:
        model = StudentResult
        fields = ['id', 'student_name', 'work_number', 'gender', 'contact_number', 'school_number',
                 'variant', 'total_score', 'exam', 'branch', 'section', 'section_name',
                 'subject_results', 'overall_stats','additional_datas','pdfToken','class_level','group','original_answers', 'group_id',
                 'specialization', 'specialization_id']

    def update(self, instance, validated_data):
        """
        Update StudentResult instance and handle nested subject_results
        """
        # Extract subject_results data if present
        subject_results_data = validated_data.pop('subject_results', None)

       
            

        # Update the main StudentResult instance
        for attr, value in validated_data.items():
            if attr == 'group':
                continue
            if attr == 'group_id':
                if value is not None:
                    try:
                        group = Group.objects.get(id=value)
                        instance.group = group
                    except Group.DoesNotExist:
                        pass
                else:
                    instance.group = None
                continue
            if attr == 'specialization':
                continue
            if attr == 'specialization_id':
                if value is not None:
                    try:
                        spec = Specialization.objects.get(id=value)
                        instance.specialization = spec
                    except Specialization.DoesNotExist:
                        pass
                else:
                    instance.specialization = None
                continue
                
            setattr(instance, attr, value)
        
        # Handle subject_results updates
        if subject_results_data is not None:
            # Get existing subject results
            existing_subject_results = {sr.subject_id: sr for sr in instance.subject_results.all()}
            
            for subject_result_data in subject_results_data:
                subject = subject_result_data.get('subject')
                
                # Handle subject field - convert to ID if it's a Subject instance
                if isinstance(subject, Subject):
                    subject_id = subject.id
                elif isinstance(subject, int):
                    subject_id = subject
                else:
                    continue  # Skip if subject is invalid
                
                if subject_id:
                    if subject_id in existing_subject_results:
                        # Update existing subject result
                        subject_result = existing_subject_results[subject_id]
                        for key, value in subject_result_data.items():
                            if key != 'subject':
                                setattr(subject_result, key, value)
                        subject_result.save()
                    else:
                        # Create new subject result
                        SubjectResult.objects.create(
                            student_result=instance,
                            subject_id=subject_id,
                            **{k: v for k, v in subject_result_data.items() if k != 'subject'}
                        )
        
        instance.save()
        return instance

        
    
    
    def get_overall_stats(self, obj):
        subject_results = obj.subject_results.all()
        total_questions = sum(sr.total_questions for sr in subject_results)
        correct_answers = sum(sr.correct_answers for sr in subject_results)
        wrong_answers = sum(sr.wrong_answers for sr in subject_results)
        empty_answers = sum(sr.empty_answers for sr in subject_results)
        
        return {
            'total_questions': total_questions,
            'correct_answers': correct_answers,
            'wrong_answers': wrong_answers,
            'empty_answers': empty_answers,
            'total_score': float(obj.total_score) if obj.total_score is not None else 0,
            'percentage': float(obj.total_score) if obj.total_score is not None else 0 / total_questions * 100 if total_questions > 0 else 0
        }
  
class CorrectAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CorrectAnswer
        fields = ['question_number', 'correct_answer','question_type', 'score', 'penalty_score', 
                 'is_multiple_choice', 'is_starred','subject']

class CorrectAnswerCombinationSerializer(serializers.ModelSerializer):
    answers = CorrectAnswerSerializer(many=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    class_name = serializers.CharField(source='class_level.name', read_only=True)
    specialization_name = serializers.CharField(source='specialization.name', read_only=True, default=None)
    
    class Meta:
        model = CorrectAnswerCombination
        fields = ['id', 'combination_uid','section', 'section_name', 'variant', 'class_level', 'class_name', 
                 'group_name', 'specialization', 'specialization_name', 'answers']

class CorrectAnswerCombinationCreateSerializer(serializers.Serializer):
    combinations = CorrectAnswerCombinationSerializer(many=True)
    
    def create(self, validated_data):
        exam = self.context['exam']
        combinations_data = validated_data['combinations']
        
        # Delete existing combinations for this exam
        CorrectAnswerCombination.objects.filter(exam=exam).delete()
        
        created_combinations = []
        for combination_data in combinations_data:
            answers_data = combination_data.pop('answers')
            combination = CorrectAnswerCombination.objects.create(
                exam=exam,

                **combination_data
            )
            
            # Create answers
            for answer_data in answers_data:
                CorrectAnswer.objects.create(
                    combination=combination,
                    **answer_data
                )
            
            created_combinations.append(combination)
        
        return created_combinations

class ExamResultSummarySerializer(serializers.ModelSerializer):
    has_errors = serializers.SerializerMethodField()
    errors = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ['id', 'name', 'date', 'type', 'participant_count', 'branch_count', 'has_errors', 'errors']
    
    def get_has_errors(self, obj):
        # Check if there are any import logs with errors
        return obj.import_logs.filter(errors__isnull=False).exists()
    
    def get_errors(self, obj):
        # Return a list of errors if has_errors is True
        if self.get_has_errors(obj):
            return list(obj.import_logs.filter(errors__isnull=False).values_list('errors', flat=True))
        return []
    def get_participant_count(self, obj):
        return obj.student_results.count()

class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    branch_id = serializers.IntegerField(required=False)
    exam_id = serializers.IntegerField(required=False)
    
    def validate_file(self, value):
        # File size validation (10MB for most files, 30MB for PDFs)
        max_size = 3072 * 1024 * 1024 if value.name.lower().endswith('.pdf') else 3072 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError(f'File size cannot exceed {max_size // (1024*1024)}MB')
        return value
    



class RecheckAnswersSerializer(serializers.Serializer):
    student_answers = serializers.DictField(
        child=serializers.CharField(),
        help_text="Dictionary with question numbers as keys and student answers as values"
    )
    foreign_language = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Foreign language code (e.g., 'I' for English, 'R' for Russian)"
    )
    
    def validate_student_answers(self, value):
        """Validate that all keys are numeric"""
        for key in value.keys():
            try:
                int(key)
            except ValueError:
                raise serializers.ValidationError(f"Question number '{key}' must be numeric")
        return value
    


class NotUploadedStudentResultSerializer(serializers.ModelSerializer):
    exam = ExamDetailSerializer(read_only=True)
    
    class Meta:
        model = NotUploadedStudentResult
        fields = ['id', 'student_name', 'work_number', 'exam']