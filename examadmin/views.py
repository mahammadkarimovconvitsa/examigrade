from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.http import HttpResponse
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.views import APIView 
from django.http import HttpResponse 
import ast
from django.contrib.auth import login, logout
from PyPDF2 import PdfReader, PdfWriter
from django.template.loader import render_to_string
from django.db.models import Q
from django.shortcuts import get_object_or_404
import zipfile
from io import BytesIO
from services.calculate import TxtImportService 
from .models import *
from .serializers import *
import pandas as pd
import json
import pdfkit 
from django.core.files import File



class CustomAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user': UserSerializer(user).data
        })

class AuthViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]
    
    @action(detail=False, methods=['post'])
    def login(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data
            },status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def logout(self, request):
        if request.user.is_authenticated:
            Token.objects.filter(user=request.user).delete()
        return Response({'message': 'Successfully logged out'})
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        if request.user.is_authenticated:
            return Response(UserSerializer(request.user).data)
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)

class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['patch'])
    def toggle_status(self, request, pk=None):
        branch = self.get_object()
        branch.is_active = not branch.is_active
        branch.save()
        return Response(self.get_serializer(branch).data)

class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['patch'])
    def toggle_status(self, request, pk=None):
        subject = self.get_object()
        subject.is_active = not subject.is_active
        subject.save()
        return Response(self.get_serializer(subject).data)

class ClassViewSet(viewsets.ModelViewSet):
    queryset = Class.objects.all()
    serializer_class = ClassSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['patch'])
    def toggle_status(self, request, pk=None):
        class_obj = self.get_object()
        class_obj.is_active = not class_obj.is_active
        class_obj.save()
        return Response(self.get_serializer(class_obj).data)

class SectionViewSet(viewsets.ModelViewSet):
    queryset = Section.objects.all()
    serializer_class = SectionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['patch'])
    def toggle_status(self, request, pk=None):
        section = self.get_object()
        section.is_active = not section.is_active
        section.save()
        return Response(self.get_serializer(section).data)

class ExamViewSet(viewsets.ModelViewSet):
    queryset = Exam.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ExamCreateSerializer
        elif self.action == 'list':
            return ExamListSerializer
        elif self.action == 'update':
            return ExamUpdateSerializer
        return ExamDetailSerializer
    
    @action(detail=True, methods=['patch'])
    def toggle_status(self, request, pk=None):
        exam = self.get_object()
        exam.is_active = not exam.is_active
        # If exam is being activated, make all student results active
        if not exam.is_active:  # This means it's going from inactive to active
            StudentResult.objects.filter(exam=exam, is_active=False).update(is_active=True)
        exam.save()
        return Response(self.get_serializer(exam).data)

    
    
    @action(detail=True, methods=['get', 'post'])
    def correct_answers(self, request, pk=None):
        exam = self.get_object()
        
        if request.method == 'GET':
            combinations = CorrectAnswerCombination.objects.filter(exam=exam)
            serializer = CorrectAnswerCombinationSerializer(combinations, many=True)
            return Response(serializer.data)
        
        elif request.method == 'POST':
            serializer = CorrectAnswerCombinationCreateSerializer(
                data=request.data, 
                context={'exam': exam}
            )
            if serializer.is_valid():
                serializer.save()
                return Response({'message': 'Correct answers saved successfully'})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def import_correct_answers(self, request, pk=None):
        exam = self.get_object()
        serializer = FileUploadSerializer(data=request.data)
        
        if serializer.is_valid():
            file = serializer.validated_data['file']
            
            try:
                # Read Excel file
                df = pd.read_excel(file)
                
                # Process the data and create correct answers
                # Implementation depends on your Excel format
                
                return Response({'message': f'Successfully imported correct answers'})
            
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """
        Duplicate an exam with all its details except student results.
        Creates a copy of exam details, correct answers, section details, and exam subjects.
        """
        original_exam = self.get_object()
        
        try:
            # Create new exam with "(kopya)" suffix
            new_exam = Exam.objects.create(
                name=f"{original_exam.name} (kopya)",
                date=original_exam.date,
                type=original_exam.type,
                participant_count=0,  # Reset participant count
                is_active=False
            )
            
            # Copy many-to-many relationships
            new_exam.branches.set(original_exam.branches.all())
            new_exam.classes.set(original_exam.classes.all())
            new_exam.sections.set(original_exam.sections.all())
            new_exam.groups.set(original_exam.groups.all())
            new_exam.specializations.set(original_exam.specializations.all())
            
            # Copy section details
            for section_detail in original_exam.section_details.all():
                new_section_detail = SectionDetail.objects.create(
                    exam=new_exam,
                    section=section_detail.section,
                    variant_count=section_detail.variant_count,
                    group=section_detail.group
                )
                
                # Copy exam subjects for this section detail
                for exam_subject in section_detail.exam_subjects.all():
                    ExamSubject.objects.create(
                        section_detail=new_section_detail,
                        group=exam_subject.group,
                        subject=exam_subject.subject,
                        question_count=exam_subject.question_count
                    )

            # Copy correct answer combinations
            for combination in original_exam.correct_answers.all():
                new_combination = CorrectAnswerCombination.objects.create(
                    exam=new_exam,
                    section=combination.section,
                    group=combination.group,
                    combination_uid=combination.combination_uid,
                    variant=combination.variant,
                    class_level=combination.class_level,
                    category=combination.category,
                    group_name=combination.group_name,
                    specialization=combination.specialization
                )
                
                # Copy correct answers for this combination
                for answer in combination.answers.all():
                    CorrectAnswer.objects.create(
                        combination=new_combination,
                        question_number=answer.question_number,
                        correct_answer=answer.correct_answer,
                        score=answer.score,
                        penalty_score=answer.penalty_score,
                        is_multiple_choice=answer.is_multiple_choice,
                        is_starred=answer.is_starred,
                        subject=getattr(answer, 'subject', None),
                        question_type=getattr(answer, 'question_type', None)
                    )
            
            # Copy correct answer combinations and their answers
           
            # Return the new exam details
            serializer = self.get_serializer(new_exam)
            return Response({
                'message': f'İmtahan uğurla kopyalandı',
                'original_exam': original_exam.name,
                'duplicated_exam': new_exam.name,
                'exam': serializer.data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ExamsViewSet(viewsets.ModelViewSet):
    serializer_class = ExamListSerializer
    permission_classes = [permissions.AllowAny]
    def get_queryset(self):
            queryset = Exam.objects.all()
            queryset = queryset.filter(is_active=True)
            return queryset
    

    

        

class StudentResultViewSet(viewsets.ModelViewSet):
    serializer_class = StudentResultSerializer
    permission_classes = [permissions.IsAuthenticated]


        

    def get_queryset(self):
        queryset = StudentResult.objects.all()
        exam_id = self.request.query_params.get('exam_id')
        branch_id = self.request.query_params.get('branch_id')
        variant = self.request.query_params.get('variant')
        section_id = self.request.query_params.get('section_id')
        search = self.request.query_params.get('search')
        
        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)
        if variant:
            queryset = queryset.filter(variant=variant)
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        if search:
            queryset = queryset.filter(
                Q(student_name__icontains=search) |
                Q(work_number__icontains=search) |
                Q(contact_number__icontains=search)
            )
        
        return queryset


    @action(detail=False, methods=['get'])
    def not_uploaded(self, request):
        exam_id = request.query_params.get('exam_id')
        if not exam_id:
            return Response({'error': 'exam_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        not_uploaded_results = NotUploadedStudentResult.objects.filter(exam_id=exam_id)
        serializer = NotUploadedStudentResultSerializer(not_uploaded_results, many=True)
        return Response(serializer.data)


    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        ids = request.data.get('student_ids', [])
        if not ids:
            return Response({'error': 'No IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
        studentss = StudentResult.objects.filter(id__in=ids)
        exam_errors = ImportLog.objects.filter(exam=studentss.first().exam)
        exam = studentss.first().exam
        unuploaded = NotUploadedStudentResult.objects.filter(exam=studentss.first().exam)
        studentss.delete()
        studentss1 = StudentResult.objects.filter(id__in=ids)
        if not studentss1.exists():
            exam_errors.delete()
            unuploaded.delete()
            exam.participant_count = StudentResult.objects.filter(exam=exam).count()
            exam.save()
        return Response({'message': f'Successfully deleted {len(ids)} results'},status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'])
    def toggle_status(self, request, pk=None):
        student_result = StudentResult.objects.get(pk=pk)
        student_result.is_active = not student_result.is_active
        student_result.save()
        return Response(self.get_serializer(student_result).data)
        
    def get_exam_id(self):
        """Get the exam_id from query parameters."""
        return self.request.query_params.get('exam_id')
    def get_branch_id(self):
        """Get the branch_id from query parameters."""
        return self.request.query_params.get('branch_id')

    @action(detail=False, methods=['post'])
    def import_results(self, request):
        serializer = FileUploadSerializer(data=request.data)
        
        if serializer.is_valid():
            file = serializer.validated_data['file']
            branch_id = serializer.validated_data.get('branch_id')
            exam_id = request.data.get('exam_id')
            recheck = int(request.data.get('recheck', 0))
            if not exam_id:
                return Response({'error': 'exam_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                # Initialize TXT import service
                import_service = TxtImportService(exam_id=exam_id, branch_id=branch_id,recheck=recheck)
                
                # Read TXT file content
                content = file.read().decode('utf-8')
                
                # Import results
                result = import_service.import_from_txt(content)
                
                if result['success']:
                    return Response({
                        'message': f'Successfully imported {result["imported_count"]} results',
                        'imported_count': result['imported_count']
                    })
                else:
                    return Response({
                        'error': 'Import completed with errors',
                        'imported_count': result['imported_count'],
                        'errors': result['errors']
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    @action(detail=False, methods=['post'])
    def recheck_answers(self, request, pk=None):
        """
        Recheck student answers with foreign language filtering
        
        Expected payload:
        {
            "student_answers": {"1": "A", "2": "B", ...},
            "foreign_language": "I"  // Optional foreign language code
        }
        """
        exam_id = request.data.get('exam_id')
        branch_id = request.data.get('branch_id')
        student_ids = request.data.get('student_ids', [])
        if not exam_id:
            return Response({'error': 'exam_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not branch_id:
            return Response({'error': 'branch_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
           
            
           
            
            # Initialize recheck service
            recheck_service = TxtImportService(exam_id=exam_id, branch_id=branch_id, recheck=True)

            recheck = recheck_service.recheck_results(work_numbers=student_ids)

            return Response({
                'message': 'Answers rechecked successfully',
                'result': recheck
            })
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


    @action(detail=True, methods=['put'])
    def upload_answer_card(self, request, pk=None):
        student_result = self.get_object()
        serializer = FileUploadSerializer(data=request.data)
        
        if serializer.is_valid():


            file = serializer.validated_data['file']
            
            # Delete old answer card if exists
            if student_result.answer_card_pdf:
                student_result.answer_card_pdf.delete()
            
            student_result.answer_card_pdf = file
            randomPdfToken = self.random_token()
            student_result.pdfToken = randomPdfToken
            student_result.save()
            return Response({'message': 'Answer card uploaded successfully'})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

    def random_token(self, length=10):
        import random
        import string

        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

class ResultCardViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['get'])
    def by_work_number(self, request):
        work_number = request.query_params.get('work_number')
        exam_id = request.query_params.get('exam_id')
        if not work_number:
            return Response({'error': 'work_number parameter is required'}, 
                            status=status.HTTP_400_BAD_REQUEST)
        if not exam_id:
            return Response({'error': 'exam_id parameter is required'}, 
                            status=status.HTTP_400_BAD_REQUEST)

        # Validate work_number
        if '*' in work_number or any(c in work_number for c in ['!', '@', '#', '$', '%', '^', '&', '(', ')']):
            return Response({'error': 'work_number contains invalid characters'}, 
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            student_result = StudentResult.objects.get(work_number=work_number, exam_id=exam_id)
            if not student_result.is_active and student_result.exam.is_active:
                return Response({'error': 'Result is inactive'}, status=status.HTTP_404_NOT_FOUND)
            subjects_results = SubjectResult.objects.filter(student_result=student_result)
            if not subjects_results.exists():
                return Response({'error': 'No result found'}, status=status.HTTP_404_NOT_FOUND)
            serializer = DetailedStudentResultSerializer(student_result)
            return Response(serializer.data)
        except StudentResult.DoesNotExist:
            return Response({'error': 'Result not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def generate_pdf(self, request):
        work_number = request.query_params.get('work_number')
        exam_id = request.query_params.get('exam_id')
        if not work_number:
            return Response({'error': 'work_number parameter is required'}, 
                            status=status.HTTP_400_BAD_REQUEST)
        if not exam_id:
            return Response({'error': 'exam_id parameter is required'}, 
                            status=status.HTTP_400_BAD_REQUEST)

        # Validate work_number
        if '*' in work_number or any(c in work_number for c in ['!', '@', '#', '$', '%', '^', '&', '(', ')']):
            return Response({'error': 'work_number contains invalid characters'}, 
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            student_result = StudentResult.objects.get(work_number=work_number, exam_id=exam_id)
            if not student_result.is_active and student_result.exam.is_active:
                return Response({'error': 'Result is inactive'}, status=status.HTTP_404_NOT_FOUND)
            subjects_results = SubjectResult.objects.filter(student_result=student_result)
            if not subjects_results.exists():
                return Response({'error': 'No result found'}, status=status.HTTP_404_NOT_FOUND)

            serializer = DetailedStudentResultSerializer(student_result)
            html_content = render_to_string("result.html", {"result": serializer.data})

            # 👉 Explicit wkhtmltopdf path
            # Linux example:
            # path_wkhtmltopdf = "/usr/bin/wkhtmltopdf"
            # Windows example:
            # path_wkhtmltopdf = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
            path_wkhtmltopdf = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"

            config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

            # PDF options for A3 page size
            options = {
                'page-size': 'A3',
                'margin-top': '0.75in',
                'margin-right': '0.75in',
                'margin-bottom': '0.75in',
                'margin-left': '0.75in',
                'encoding': "UTF-8",
                'no-outline': None
            }

            # Convert HTML → PDF
            pdf_file = pdfkit.from_string(html_content, False, options=options, configuration=config)

            # Return as downloadable response
            response = HttpResponse(pdf_file, content_type="application/pdf")
            response["Content-Disposition"] = "attachment; filename=result.pdf"
            return response

        except StudentResult.DoesNotExist:
            return Response({'error': 'Result not found'}, status=status.HTTP_404_NOT_FOUND)
class ResultsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        exams = Exam.objects.all()
        serializer = ExamResultSummarySerializer(exams, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_work_number(self, request):
        work_number = request.query_params.get('work_number')
        exam_id = request.query_params.get('exam_id')
        if not work_number:
            return Response({'error': 'work_number parameter is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        if not exam_id:
            return Response({'error': 'exam_id parameter is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)

        # Validate work_number for problematic characters
       
        try:
            student_result = StudentResult.objects.get(work_number=work_number, exam_id=exam_id)
          
            serializer = DetailedStudentResultSerializer(student_result)
            return Response(serializer.data)
        except StudentResult.DoesNotExist:
            return Response({'error': 'Result not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False,methods=['put'])
    def update_student_result(self, request):
        work_number = request.query_params.get('work_number')
        exam_id = request.query_params.get('exam_id')
        if not work_number:
            return Response({'error': 'work_number parameter is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        if not exam_id:
            return Response({'error': 'exam_id parameter is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)

        try:
            student_result = StudentResult.objects.get(work_number=work_number, exam_id=exam_id)
            
            # Check if subject_results are being updated
            subject_results_data = request.data.get('subject_results')
            if subject_results_data:
                # Reconstruct original_answers from subject_results
                original_answers = self._reconstruct_original_answers(subject_results_data)
                request.data['original_answers'] = json.dumps(original_answers, ensure_ascii=False)
            
            serializer = DetailedStudentResultSerializer(student_result, data=request.data, partial=True)
            if serializer.is_valid():
                # Handle subject_results updates manually
                if subject_results_data:
                    # Update subject results
                    for subject_result_data in subject_results_data:
                        subject_id = subject_result_data.get('subject')
                        if subject_id:
                            subject_result, created = SubjectResult.objects.get_or_create(
                                student_result=student_result,
                                subject_id=subject_id,
                                defaults=subject_result_data
                            )
                            if not created:
                                # Update existing subject result
                                for key, value in subject_result_data.items():
                                    if key != 'subject':
                                        setattr(subject_result, key, value)
                                subject_result.save()
                
                # Save the main student result
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                        
        except StudentResult.DoesNotExist:
            return Response({'error': 'Result not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def _reconstruct_original_answers(self, subject_results_data):
        """
        Reconstruct original_answers from subject_results data
        Convert processed answers back to original TXT file format
        """
        original_answers = []
        
        for subject_result in subject_results_data:
            subject_data = subject_result.get('subject_data', [])
            
            for question_data in subject_data:
                question_number = question_data.get('question_number')
                student_answer = question_data.get('student_answer', '')
                question_type = question_data.get('question_type', 'close')
                
                if question_number:
                    # Convert processed answer back to original format
                    if question_type == 'matching' and ';' in student_answer:
                        # For matching questions, convert semicolon-separated back to 15-character format
                        original_answer = self._convert_to_15_char_format(student_answer)
                        original_answers.append(original_answer)
                    else:
                        # For other question types, use as-is
                        original_answers.append(student_answer)

        return original_answers
    
    def _convert_to_15_char_format(self, semicolon_separated_answer):
        """
        Convert semicolon-separated answer back to 15-character format
        Example: "ac;bd;e" -> "ac   bd   e    "
        """
        if not semicolon_separated_answer or semicolon_separated_answer.strip() == '':
            return '               '  # 15 spaces for empty answer
        
        choices = semicolon_separated_answer.split(';')
        formatted_choices = []
        
        for choice in choices:
            # Pad each choice to 5 characters
            formatted_choice = choice.ljust(5)[:5]  # Ensure exactly 5 characters
            formatted_choices.append(formatted_choice)
        
        # Ensure we have exactly 3 choices (padding with empty 5-char strings if needed)
        while len(formatted_choices) < 3:
            formatted_choices.append('     ')  # 5 spaces
        
        # Join and ensure exactly 15 characters
        result = ''.join(formatted_choices[:3])
        return result[:15].ljust(15)  # Ensure exactly 15 characters


    @action(detail=True, methods=['get'])
    def exam_results(self, request, pk=None):
        exam = get_object_or_404(Exam, pk=pk)
        results = StudentResult.objects.filter(exam=exam)
        
        # Apply filters
        branch_ids = request.query_params.getlist('branch_ids[]')
        variants = request.query_params.getlist('variants[]')
        sections = request.query_params.getlist('sections[]')
        search = request.query_params.get('search')
        
        if branch_ids:
            results = results.filter(branch_id__in=branch_ids)
        if variants:
            results = results.filter(variant__in=variants)
        if sections:
            results = results.filter(section__name__in=sections)
        if search:
            results = results.filter(
                Q(student_name__icontains=search) |
                Q(work_number__icontains=search) |
                Q(contact_number__icontains=search)
            )
        
        serializer = StudentResultSerializer(results, many=True)
        return Response(serializer.data)





class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['patch'])
    def toggle_status(self, request, pk=None):
        group = self.get_object()
        group.is_active = not group.is_active
        group.save()
        return Response(self.get_serializer(group).data)

class SpecializationViewSet(viewsets.ModelViewSet):
    queryset = Specialization.objects.all()
    serializer_class = SpecializationSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['patch'])
    def toggle_status(self, request, pk=None):
        specialization = self.get_object()
        specialization.is_active = not specialization.is_active
        specialization.save()
        return Response(self.get_serializer(specialization).data)


class GetStatsViewSet(viewsets.ViewSet):
            permission_classes = [permissions.IsAuthenticated]

            @action(detail=False, methods=['get'])
            def get_stats(self, request):
                total_exam_count = Exam.objects.count()
                total_participant_count = StudentResult.objects.count()
                total_branch_count = Branch.objects.count()
                average_total_score = StudentResult.objects.aggregate(
                    avg_score=models.Avg('total_score')
                )['avg_score'] or 0

                return Response({
                    'total_exam_count': total_exam_count,
                    'total_participant_count': total_participant_count,
                    'total_branch_count': total_branch_count,
                    'average_total_score': round(average_total_score,2),
                })

class GetAnswerCardViewSet(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request,*args,**kwargs):
        try:
            student_number = request.query_params.get('student_number')
            exam_id = request.query_params.get('exam_id')
            pdf_token = request.query_params.get('token')
            if not student_number or not exam_id or not pdf_token:
                return Response({'error': 'student_number, exam_id and pdf_token parameters are required'}, 
                                status=status.HTTP_400_BAD_REQUEST)
            
            student_result = StudentResult.objects.get(
                work_number=student_number, 
                exam_id=exam_id, 
                pdfToken=pdf_token
            )
        except StudentResult.DoesNotExist:
            return HttpResponse('Xəta: Cavab kartı tapılmadı. İmtahan mərkəzi ilə əlaqə saxlamağınız xahiş olunur!', status=404)

        response = HttpResponse(student_result.answer_card_pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{student_result.work_number}_answer_card.pdf"'
        return response
    

class ExportViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def export_results(self, request):
        exam_id = request.query_params.get('exam_id')
        if not exam_id:
            return Response({'error': 'exam_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        if request.query_params.get('student_ids'):
            student_ids = request.query_params.getlist('student_ids')
            student_ids = request.query_params.get('student_ids')
            if isinstance(student_ids, str):
                try:
                    student_ids = ast.literal_eval(student_ids)
                    if not isinstance(student_ids, list):
                        student_ids = [student_ids]
                except Exception:
                    return Response({'error': 'Invalid student_ids format'}, status=status.HTTP_400_BAD_REQUEST)
            results = StudentResult.objects.filter(exam_id=exam_id, id__in=student_ids)
        else:
            results = StudentResult.objects.filter(exam_id=exam_id)

        if not results.exists():
            return Response({'error': 'No results found for this exam'}, status=status.HTTP_404_NOT_FOUND)
        
        # Convert to DataFrame
        data = []
        for result in results:
            detailed_result = DetailedStudentResultSerializer(result).data
            student_data = {
                'Is nomresi': detailed_result['work_number'],
                'Ad və Soyad': detailed_result['student_name'],
                'Cins': 'Kişi' if detailed_result['gender'] == 'K' else 'Qadın',
                'Əlaqə Nömrəsi': detailed_result['contact_number'],
                'Filial': detailed_result['branch']['name'],
                'İmtahan tarixi': detailed_result['exam']['date'],
                'Bölmə': detailed_result['section_name'] if detailed_result['section_name'] else '',
                'Sinif': result.class_level.name if result.class_level else '',
                'İxtisas': detailed_result['specialization']['name'] if detailed_result['specialization']['name'] else '',
                'Peşə': detailed_result['additional_datas']['peshe'] if detailed_result['additional_datas']['peshe'] else '',
                'Variant': detailed_result['variant'],
                'Məktəb Nömrəsi': "",
                'Ümumi Bal': str(detailed_result['total_score']).replace('.',','),
                'Düzgün Cavablar': detailed_result['overall_stats']['correct_answers'],
                'Səhv Cavablar': detailed_result['overall_stats']['wrong_answers'],
                'Boş Qalanlar': detailed_result['overall_stats']['empty_answers']
                
                
            }
            if result.group:
                student_data['Qrup'] = result.group.name
            if result.class_level:
                student_data['Sinif'] = result.class_level.name
            if result.school_number:
                student_data['Məktəb Nömrəsi'] = result.school_number
            for subject_result in SubjectResult.objects.filter(student_result=result):
                student_data[subject_result.subject.name] = str(subject_result.score).replace('.',',')
            data.append(student_data)
         
        
        df = pd.DataFrame(data)
        
        # Create a CSV response
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="exam_{exam_id}_results.xlsx"'
        df.to_excel(excel_writer=response, index=False)

        return response
    @action(detail=False, methods=['get'])
    def export_answer_cards(self, request):
        exam_id = request.query_params.get('exam_id')
        student_ids = request.query_params.get('student_ids')
        student_ids = ast.literal_eval(student_ids) if student_ids else []

        if not exam_id:
            return Response({'error': 'exam_id is required'}, status=status.HTTP_400_BAD_REQUEST)
      
        if student_ids:
            results = StudentResult.objects.filter(exam_id=exam_id, id__in=student_ids)
        else:
            return Response({'error': 'student_ids parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        exam = get_object_or_404(Exam, id=exam_id)

        if not results.exists():
            return Response({'error': 'No results found for this exam and branch'}, status=status.HTTP_404_NOT_FOUND)

        # ZIP faylı üçün buffer
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            for result in results:
                subjects_results = SubjectResult.objects.filter(student_result=result)
                if not subjects_results.exists():
                    continue  # nəticəsi olmayan tələbəni keç

                # 🔹 1. Nəticə PDF-i render et
                serializer = DetailedStudentResultSerializer(result)
                html_content = render_to_string("result.html", {"result": serializer.data})

                path_wkhtmltopdf = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
                config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
                
                # PDF options for A3 page size
                options = {
                    'page-size': 'A3',
                    'margin-top': '0.75in',
                    'margin-right': '0.75in',
                    'margin-bottom': '0.75in',
                    'margin-left': '0.75in',
                    'encoding': "UTF-8",
                    'no-outline': None
                }
                
                result_pdf = pdfkit.from_string(html_content, False, options=options, configuration=config)

                # 🔹 2. PdfWriter aç
                output = PdfWriter()

                # Render olunmuş nəticəni əlavə et
                result_reader = PdfReader(BytesIO(result_pdf))
                for page in result_reader.pages:
                    output.add_page(page)
                # 🔹 4. Yekun PDF-i yaddaşa yaz
                combined_pdf = BytesIO()
                output.write(combined_pdf)
                combined_pdf.seek(0)

                # 🔹 5. ZIP-ə əlavə et
                file_name = f"{result.total_score}_{result.work_number}_{result.student_name.replace(' ', '_').replace('*','')}{'_'+result.class_level.name if result.class_level else ''}{'_'+result.section.name if result.section else ''}{'_' + result.group.name if result.group else ''}_result.pdf"
                zip_file.writestr(file_name, combined_pdf.getvalue())

        # ZIP-i cavab olaraq qaytar
        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="cavab_kartlari.zip"'
        return response
    

    @action(detail=False, methods=['post'])
    def import_answer_cards(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Starting import_answer_cards with data: {request.data.keys()}")
            
            serializer = FileUploadSerializer(data=request.data)
            
            if not serializer.is_valid():
                logger.error(f"Serializer validation failed: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            file = serializer.validated_data['file']
            exam_id = request.data.get('exam_id')
            
            logger.info(f"Processing file: {file.name}, exam_id: {exam_id}")

            if not exam_id:
                return Response({'error': 'exam_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Convert exam_id to integer and validate
            try:
                exam_id = int(exam_id)
                logger.info(f"Converted exam_id to integer: {exam_id}")
            except (ValueError, TypeError):
                return Response({'error': 'exam_id must be a valid integer'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify exam exists
            try:
                exam = Exam.objects.get(id=exam_id)
                logger.info(f"Found exam: {exam.name}")
            except Exam.DoesNotExist:
                return Response({'error': f'Exam with id {exam_id} not found'}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                # ZIP faylını oxu
                with zipfile.ZipFile(file, 'r') as zip_file:
                    logger.info(f"ZIP file opened successfully, contains {len(zip_file.infolist())} files")
                    
                    updated_count = 0
                    errors = []
                    processed_files = []
                    
                    for file_info in zip_file.infolist():
                        try:
                            # Skip directories
                            if file_info.is_dir():
                                continue
                                
                            # Fayl adından iş nömrəsini çıxar
                            file_name = file_info.filename
                            logger.info(f"Processing file: {file_name}")
                            
                            # Handle file names with path separators
                            base_name = file_name.split('/')[-1]  # Get filename without path
                            # Also handle Windows path separators
                            base_name = base_name.split('\\')[-1]
                            
                            if not base_name or not base_name.strip():
                                logger.warning(f"Empty base_name for file: {file_name}")
                                continue
                                
                            # Remove extension to get work_number
                            if '.' in base_name:
                                work_number = base_name.rsplit('.', 1)[0]  # Use rsplit to handle multiple dots
                            else:
                                work_number = base_name
                            
                            if not work_number or not work_number.strip():
                                errors.append(f"Could not extract work number from file: {file_name}")
                                logger.warning(f"Could not extract work_number from: {file_name}")
                                continue
                            
                            # Clean work_number of any special characters that might cause issues
                            work_number = work_number.strip()
                            
                            logger.info(f"Extracted work_number: '{work_number}'")
                            
                            # Tələbə nəticəsini tap
                            try:
                                student_result = StudentResult.objects.get(
                                    work_number=work_number,
                                    exam_id=exam_id
                                )
                                logger.info(f"Found student result for work_number: {work_number}")
                            except StudentResult.DoesNotExist:
                                error_msg = f"Work number '{work_number}' not found in exam {exam_id}"
                                errors.append(error_msg)
                                logger.warning(error_msg)
                                continue
                            except Exception as lookup_error:
                                error_msg = f"Database error looking up work_number '{work_number}': {str(lookup_error)}"
                                errors.append(error_msg)
                                logger.error(error_msg, exc_info=True)
                                continue
                            
                            # Mövcud cavab kartını sil
                            if student_result.answer_card_pdf:
                                try:
                                    student_result.answer_card_pdf.delete()
                                    logger.info(f"Deleted existing answer card for {work_number}")
                                except Exception as delete_error:
                                    logger.warning(f"Could not delete existing file for {work_number}: {delete_error}")
                            
                            # Yeni cavab kartını yüklə
                            try:
                                with zip_file.open(file_info) as pdf_file:
                                    file_content = pdf_file.read()
                                    
                                    # Validate file content is not empty
                                    if not file_content:
                                        error_msg = f"Empty file content for {file_name}"
                                        errors.append(error_msg)
                                        logger.warning(error_msg)
                                        continue
                                    
                                    logger.info(f"Read {len(file_content)} bytes from {file_name}")
                                    
                                    django_file = File(BytesIO(file_content), name=base_name)
                                    student_result.answer_card_pdf.save(base_name, django_file)
                                    randomPdfToken = self.random_token()
                                    student_result.pdfToken = randomPdfToken
                                    student_result.save()
                                    updated_count += 1
                                    processed_files.append(work_number)
                                    logger.info(f"Successfully updated answer card for {work_number}")
                            except Exception as file_error:
                                error_msg = f"Error reading/saving file {file_name}: {str(file_error)}"
                                errors.append(error_msg)
                                logger.error(error_msg, exc_info=True)
                                continue
                        
                        except Exception as e:
                            error_msg = f"Error processing {file_name}: {str(e)}"
                            errors.append(error_msg)
                            logger.error(error_msg, exc_info=True)
                
                message = f'Successfully updated {updated_count} answer cards.'
                if errors:
                    message += f' However, {len(errors)} errors occurred.'
                
                logger.info(f"Import completed. Updated: {updated_count}, Errors: {len(errors)}")
                
                return Response({
                    'message': message,
                    'updated_count': updated_count,
                    'error_count': len(errors),
                    'errors': errors[:10],  # Limit errors in response
                    'processed_files': processed_files[:10]  # Limit files in response
                })
            
            except zipfile.BadZipFile as e:
                logger.error(f"Bad ZIP file: {str(e)}")
                return Response({'error': 'Uploaded file is not a valid ZIP'}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                logger.error(f"Unexpected error in ZIP processing: {str(e)}", exc_info=True)
                return Response({'error': f'Error processing ZIP file: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except Exception as e:
            logger.error(f"Unexpected error in import_answer_cards: {str(e)}", exc_info=True)
            return Response({'error': f'Internal server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def random_token(self, length=10):
        import random
        import string


        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))