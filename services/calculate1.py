# services/txt_import_service.py
import re
from typing import List, Dict, Tuple, Optional
from decimal import Decimal
from examadmin.models import Exam,Class,NotUploadedStudentResult, StudentResult, SubjectResult, CorrectAnswerCombination, CorrectAnswer, Branch, Section, Subject, Group
from examadmin.models import ImportLog
import random

class TxtImportService:
    """
    Service for importing student results from TXT files
    Handles different exam types with specific data structures and scoring formulas
    """
    
    EXAM_TYPE_PARSERS = {
        '9-cu sinif buraxılış': 'parse_9th_grade',
        '11-ci sinif buraxılış': 'parse_11th_grade', 
        'Blok imtahanı': 'parse_block_exam',
        'Dövlət Qulluğu': 'parse_government_service',
        'Magistratura': 'parse_magistr_service',
        'Bilik yarışı': 'parse_magistr_with_class',
        'Təkmilləşdirmə': 'parse_magistr_with_class',
        'Müəllimlərin İşə Qəbulu': 'parse_magistr_service',
        'Sertifikasiya': 'parse_magistr_service',
    }
    
    QUESTION_TYPES = {
        'closed': 'qapalı',           # A,B,C,D,E
        'open': 'açıq',               # 134,21
        'explained_open': 'izahlı_açıq',  # 1,1/3,2/3,1/2,0
        'choice': 'seçim',            # 1-ac,2-bd,3-e
        'multiple_choice': 'çox_seçimli'  # ABAB
    }
    

    def __init__(self, exam_id: int, branch_id: int, recheck: bool = False):
        self.exam = Exam.objects.get(id=exam_id)
        self.branch = Branch.objects.get(id=branch_id)
        self.recheck = recheck
        self.correct_answers = self._load_correct_answers()
        self.errors = []
        self.imported_count = 0

    def _load_correct_answers(self) -> Dict:
        """Load correct answers for the exam"""
        answers = {}
        combinations = CorrectAnswerCombination.objects.filter(exam=self.exam)
        
        for combination in combinations:
            key = f"{combination.section.name[0]}_{combination.variant}"
            if combination.class_level:
                key = f"{combination.class_level_id}_" + key
            if combination.group_name:
                key = f"{combination.group_name}_" + key
            if combination.category:
                key = f"{combination.category}_" + key
                
            answers[key] = {}
            # Use direct query instead of related manager
            correct_answers_qs = CorrectAnswer.objects.filter(combination=combination)
            
            for answer in correct_answers_qs:
                answers[key][answer.question_number] = {
                    'correct_answer': answer.correct_answer,
                    'score': answer.score,
                    'penalty_score': answer.penalty_score,
                    'is_multiple_choice': answer.is_multiple_choice,
                    'is_starred': answer.is_starred,
                    'question_type': getattr(answer, 'question_type', 'closed')
                }
        
        return answers

    def import_from_txt(self, file_content: str) -> Dict:
        """Main import method"""
        lines = file_content.split('\n')
        results = []
        
        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue
                
            student_data = None
            try:
                student_data = self._parse_line(line.strip())
                if student_data:
                    student_result = self._create_student_result(student_data)
                    if student_result:  # Only append if creation was successful
                        results.append(student_result)
                        self.imported_count += 1
            except Exception as e:
                # Log error and continue with next line
                self.errors.append(f"Sətir {line_num}: {str(e)}")
                if student_data:
                    try:
                        NotUploadedStudentResult.objects.create(
                            exam=self.exam,
                            student_name=student_data.get('student_name'),
                            work_number=student_data.get('work_number')
                        )
                    except Exception as db_error:
                        self.errors.append(f"Sətir {line_num}: DB xətası - {str(db_error)}")
                continue  # Continue with next line
        
        # Create import log
        try:
            ImportLog.objects.create(
                exam=self.exam,
                branch=self.branch,
                import_type='results',
                file_name=f'imported_results_{self.exam.name}_{self.branch.name}.txt',
                file_size=len(file_content),
                records_imported=self.imported_count,
                errors=self.errors,
            )
        except Exception as log_error:
            self.errors.append(f"Import log xətası: {str(log_error)}")
            
        return {
            'success': True,
            'imported_count': self.imported_count,
            'errors': self.errors,
            'results': results
        }




    def _parse_line(self, line: str) -> Optional[Dict]:
        """Parse line based on exam type"""
        parser_method = self.EXAM_TYPE_PARSERS.get(self.exam.type)
        
        # If exam type is not in the predefined parsers, use magistr_service as default
        if not parser_method:
            # Check if exam type includes class data
            exam_types_with_class = ['Bilik yarışı', 'Təkmilləşdirmə']
            
            if self.exam.type in exam_types_with_class:
                parser_method = 'parse_magistr_with_class'
            else:
                parser_method = 'parse_magistr_service'
        
        return getattr(self, parser_method)(line)

    def parse_9th_grade(self, line: str) -> Dict:
        """
        Parse 9th grade graduation exam data
        Format: "ABCCD;ABCCDEe *i;0123456789;K;012345;A;B;8;078;R;..."
        """
        parts = line.split(';')
        if len(parts) < 10:
            raise ValueError("9-cu sinif məlumatları natamam")
        # Replace specific characters in student name
        parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        
        return {
            'student_name': f"{parts[0].strip()} {parts[1].strip()}",
            'contact_number': parts[2].strip(),
            'gender': parts[3].strip(),
            'work_number': parts[4].strip(),
            'section': parts[5].strip(),
            'variant': parts[6].strip(),
            'class_level': '9',
            'foreign_language': parts[9].strip(),
            'answers': parts[10:] if len(parts) > 10 else []
        }

    def parse_11th_grade(self, line: str) -> Dict:
        """
        Parse 11th grade graduation exam data
        Format: "AYTeN;ABBASOVA;0775821888;Q;102124;A;A;11;056;I;..."
        """
        parts = line.split(';')
        if len(parts) < 10:
            raise ValueError("11-ci sinif məlumatları natamam")
        parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        
        return {
            'student_name': f"{parts[0].strip()} {parts[1].strip()}",
            'contact_number': parts[2].strip(),
            'work_number': parts[4].strip(),
            'gender': parts[3].strip(),
            'section': parts[5].strip(),
            'variant': parts[6].strip(),
            'class_level': '11',
            'answers': parts[10:] if len(parts) > 10 else []
        }

    def parse_block_exam(self, line: str) -> Dict:
        """
        Parse block exam data
        Format: "ABCCDEeFGg;ACDeGHIJQLNO;0123456789;K;012345;R;B;M;1RI;..."
        """
        parts = line.split(';')
        if len(parts) < 9:
            raise ValueError("Blok imtahanı məlumatları natamam")
        parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        
        return {
            'student_name': f"{parts[0].strip()} {parts[1].strip()}",
            'contact_number': parts[2].strip(),
            'work_number': parts[4].strip(),
            'section': parts[5].strip(),
            'variant': parts[6].strip(),
            'class_level': parts[7].strip(),
            'group': parts[8].strip(),
            'answers': parts[9:] if len(parts) > 9 else []
        }

    def parse_government_service(self, line: str) -> Dict:
        """
        Parse government service exam data
        Format: "PeRViZ;BiLisZADe;0707163550;K;123456;A;C;BA;..."
        """
        parts = line.split(';')
        if len(parts) < 8:
            raise ValueError("Dövlət qulluğu məlumatları natamam")
        parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        
        return {
            'student_name': f"{parts[0].strip()} {parts[1].strip()}",
            'contact_number': parts[2].strip(),
            'work_number': parts[4].strip(),
            'section': parts[5].strip(),
            'variant': parts[6].strip(),
            'category': parts[7].strip(),
            'answers': parts[8:] if len(parts) > 8 else []
        }

    def parse_magistr_service(self, line: str) -> Dict:
        """
        Parse magistr/default exam data (without class level)
        Format: "PeRViZ;BiLisZADe;0707163550;K;123456;A;B;F;..."
        """
        parts = line.split(';')
        if len(parts) < 8:
            raise ValueError("Magistr məlumatları natamam")
        parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        
        return {
            'student_name': f"{parts[0].strip()} {parts[1].strip()}",
            'contact_number': parts[2].strip(),
            'work_number': parts[4].strip(),
            'section': parts[5].strip(),
            'variant': parts[6].strip(),
            'foreign_subject': parts[7].strip(),
            'answers': parts[8:] if len(parts) > 8 else []
        }

    def parse_magistr_with_class(self, line: str) -> Dict:
        """
        Parse magistr exam data with class level (for Bilik yarışı, Təkmilləşdirmə)
        Format: "AYTeN;ABBASOVA;sA*iN;056;077435431;12485;05; ;Q;A;A;A;i;ADBEACC DB C DB BCDCBABDE;ABCDECCBABCDEDDDCCBABCBAC;...;"
        Fields:
        0: Ad
        1: Soyad
        2: Telefon
        3: Cins
        4: Is nomresi
        5: Sinif
        6: Bolme
        7: Variant
        8: Qruo
        9: Xarici dil
        10: Mekteb kodu
        11+: Cavablar
        
        """
        parts = line.split(';')
        if len(parts) < 13:
            raise ValueError("Sinif məlumatları ilə imtahan məlumatları natamam")
        
        # Replace specific characters in student name parts
        parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
        
        
        # Extract contact number - clean it from any special characters
        contact_number = parts[2].strip().replace('*', '').replace(' ', '')
        
        # Combine answers from parts 13 onwards, removing empty parts
        answers = []
        for i in range(11, len(parts)):
            answer_part = parts[i].strip()
            if answer_part:  # Only add non-empty parts
                # Split the answer part into individual characters/answers
                for char in answer_part.replace(' ', ''):
                    if char:  # Only add non-empty characters
                        answers.append(char)
        
        return {
            'student_name': f"{parts[0].strip()} {parts[1].strip()} ",
            'contact_number': contact_number,
            'school_number': parts[10].strip(),  # Məktəb nömrəsi
            'work_number': parts[4].strip(),
            'class_level': str(int(parts[5].strip())).strip(),  # Sinif
            'gender': parts[3].strip(),  # Cinsi (Q/K)
            'section': parts[6].strip(),
            'variant': parts[7].strip(),
            'foreign_language': parts[9].strip(),
            'answers': answers
        }

    def _create_student_result(self, student_data: Dict) -> Optional[StudentResult]:
        """Create student result with calculated scores"""
        try:
            # Get section object
            section = Section.objects.filter(name__startswith=student_data['section']).first()
            if not section:
                raise ValueError(f"Bölmə tapılmadı: {student_data['section']}")
            
        except Section.DoesNotExist:
            raise ValueError(f"Bölmə tapılmadı: {student_data['section']}")


        existing_student = StudentResult.objects.filter(
            exam=self.exam,
            work_number=student_data['work_number']
        ).first()
        existing_subject_results = SubjectResult.objects.filter(
            student_result__exam=self.exam,
            student_result__work_number=student_data['work_number']
        )

        if existing_student and existing_subject_results.exists() and not self.recheck:
            # Generate a random digit number with the same length as the existing work number
            new_work_number = ''.join(random.choices('0123456789', k=len(student_data['work_number'])))
            student_data['work_number'] = new_work_number
            self.errors.append(
            f"{existing_student.work_number} iş nömrəli tələbə mövcuddur: {existing_student.student_name} ({existing_student.contact_number}). "
            f"Yeni tələbə {student_data['student_name']} {student_data['contact_number']} İş nömrəsi dəyişdirildi: {new_work_number}"
            )
            student_result = StudentResult.objects.create(
                exam=self.exam,
                student_name=student_data['student_name'],
                work_number=student_data['work_number'],
                gender=student_data['gender'],
                contact_number=student_data['contact_number'],
                branch=self.branch,
                variant=student_data['variant'],
                class_level=Class.objects.filter(name=student_data.get('class_level', '')).first() if student_data.get('class_level') else None,
                section=section,
                group=Group.objects.filter(name=student_data.get('group', '')).first() if student_data.get('group') else None,

            )
        elif existing_student and not existing_subject_results.exists() and self.recheck:
            student_result = StudentResult.objects.get(
                exam=self.exam,
                work_number=student_data['work_number'],
            )
            student_result.section = section
            student_result.student_name = student_data['student_name']
            student_result.contact_number = student_data['contact_number']
            student_result.gender = student_data['gender']
            student_result.branch = self.branch
            student_result.variant = student_data['variant']
            student_result.class_level = Class.objects.filter(name=student_data.get('class_level', '')).first() if student_data.get('class_level') else None
            student_result.group = Group.objects.filter(name=student_data.get('group', '')).first() if student_data.get('group') else None



        elif existing_student and existing_subject_results.exists() and self.recheck:
            student_result = StudentResult.objects.get(
                exam=self.exam,
                work_number=student_data['work_number'],
            )
            student_result.section = section
            student_result.student_name = student_data['student_name']
            student_result.contact_number = student_data['contact_number']
            student_result.gender = student_data['gender']
            student_result.branch = self.branch
            student_result.variant = student_data['variant']
            student_result.class_level = Class.objects.filter(name=student_data.get('class_level', '')).first() if student_data.get('class_level') else None
            student_result.group = Group.objects.filter(name=student_data.get('group', '')).first() if student_data.get('group') else None

            
        else:
            student_result = StudentResult.objects.create(
                exam=self.exam,
                student_name=student_data['student_name'],
                work_number=student_data['work_number'],
                gender=student_data['gender'],
                contact_number=student_data['contact_number'],
                branch=self.branch,
                variant=student_data['variant'],
                class_level=Class.objects.filter(name=student_data.get('class_level', '')).first() if student_data.get('class_level') else None,
                section=section,
                group=Group.objects.filter(name=student_data.get('group', '')).first() if student_data.get('group') else None,
                
            )
                
        # Check if a student with the same name and contact number exists
                # Calculate scores

        existing_subject_results.delete()
        total_score, subject_results = self._calculate_scores(student_data)
        if self.exam.type == '9-cu sinif buraxılış' :
            subject_results[0]['score'] = (subject_results[0]['score'] * 100)/30
            subject_results[1]['score'] = (subject_results[1]['score'] * 100)/34
            subject_results[2]['score'] = (subject_results[2]['score'] * 100)/29
            total_score = subject_results[0]['score'] + subject_results[1]['score'] + subject_results[2]['score']
        if self.exam.type == '11-ci sinif buraxılış' :
            subject_results[0]['score'] = (subject_results[0]['score'] * 100)/37
            subject_results[1]['score'] = (subject_results[1]['score'] * 5)/2
            subject_results[2]['score'] = (subject_results[2]['score'] * 25)/8
            total_score = subject_results[0]['score'] + subject_results[1]['score'] + subject_results[2]['score']
        # Create student result
        if total_score < 0:
            total_score = Decimal('0')

        student_result.total_score = total_score
        student_result.save()
       


        # Create subject results
        for subject_data in subject_results:
            SubjectResult.objects.create(
                student_result=student_result,
                subject_id=subject_data['subject_id'],
                total_questions=subject_data['total_questions'],
                correct_answers=subject_data['correct_answers'],
                wrong_answers=subject_data['wrong_answers'],
                empty_answers=subject_data['empty_answers'],
                score=subject_data['score'],
                percentage=subject_data['percentage'],
                subject_data=subject_data['subject_data']
            )

        return student_result

    def _calculate_scores(self, student_data: Dict) -> Tuple[Decimal, List[Dict]]:
        """Calculate total score and subject scores"""
        # Get correct answers key
        answers_key = self._get_answers_key(student_data)
        correct_answers = self.correct_answers.get(answers_key, {})
        
        if not correct_answers:
            raise ValueError(f"Bu parametrlər üçün düzgün cavablar tapılmadı: {answers_key} {self.correct_answers.keys()}")

        total_score = Decimal('0')
        subject_results = []
        
        # Get exam structure for subjects
        section_details = self.exam.section_details.filter(
            section__name__startswith=student_data['section']
        ).first()
        
        if not section_details:
            raise ValueError(f"Bölmə detalları tapılmadı: {student_data['section']}")

        # Get student's selected foreign language from the answer card (if applicable)
        student_foreign_language = student_data.get('foreign_language', '').strip()
        student_foreign_subject = student_data.get('foreign_subject', '').strip()
        
        # Get all foreign language subjects in this exam
        foreign_language_subjects = []
        for exam_subject in section_details.exam_subjects.all():
            if exam_subject.subject.is_foreign_language:
                foreign_language_subjects.append(exam_subject.subject.name)

        current_question = 1
        
        # Track if we have any foreign language subjects and if they were all skipped
        has_foreign_language_subjects = False
        all_foreign_language_skipped = True

        for exam_subject in section_details.exam_subjects.all():
            # Check if this is a foreign language subject
            if exam_subject.subject.is_foreign_language:
                has_foreign_language_subjects = True
                # Skip this subject if:
                # 1. Student has selected a foreign language and it doesn't match this subject
                # 2. Or student has selected a foreign subject and it doesn't match this subject
                should_skip = False
                
                if student_foreign_language and not self._is_matching_foreign_language(
                    exam_subject.subject.name, student_foreign_language
                ):
                    should_skip = True
                elif student_foreign_subject and not self._is_matching_foreign_language(
                    exam_subject.subject.name, student_foreign_subject
                ):
                    should_skip = True
                
                if should_skip:
                    # Skip this subject but still increment question counter
                    current_question += exam_subject.question_count
                    continue
                else:
                    # At least one foreign language subject was not skipped
                    all_foreign_language_skipped = False

            # If there are foreign language subjects and all were skipped, skip this subject too
            
            subject_score = Decimal('0')
            subject_data = []
            correct_count = 0
            wrong_count = 0
            empty_count = 0
            
            # Process questions for this subject
            for q in range(exam_subject.question_count):
                question_num = current_question + q
                student_answer = student_data['answers'][question_num-1] if question_num <= len(student_data['answers']) else ''
                
                if question_num in correct_answers:
                    question_score = self._calculate_question_score(
                        student_answer,
                        correct_answers[question_num]
                    )
                    
                    # Ensure question_score is never None
                    if question_score is None:
                        question_score = Decimal('0')
                    
                    subject_score += question_score
                    
                    if question_score > Decimal('0'):
                        correct_count += 1
                        subject_data.append({"student_answer": student_answer,"result":"+","question_score": str(question_score),"correct_answer": correct_answers[question_num]['correct_answer'],"question_number": question_num})
                    elif student_answer.strip():
                        subject_data.append({"student_answer": student_answer,"result":"-","question_score": str(question_score),"correct_answer": correct_answers[question_num]['correct_answer'],"question_number": question_num})
                        wrong_count += 1
                    else:
                        subject_data.append({"student_answer": student_answer,"result":" ","question_score": str(question_score),"correct_answer": correct_answers[question_num]['correct_answer'],"question_number": question_num})
                        empty_count += 1
                    
            if subject_score < 0:
                subject_score = Decimal('0')
            total_score += subject_score

            # Calculate percentage
            max_possible_score = sum(
                correct_answers[current_question + i]['score'] 
                for i in range(exam_subject.question_count)
                if (current_question + i) in correct_answers
            )
            
            percentage = (subject_score / max_possible_score * 100) if max_possible_score > 0 else 0
            
            subject_results.append({
                'subject_id': exam_subject.subject.id,
                'total_questions': exam_subject.question_count,
                'correct_answers': correct_count,
                'wrong_answers': wrong_count,
                'empty_answers': empty_count,
                'score': subject_score,
                'percentage': percentage,
                'subject_data': subject_data
            })
            
            current_question += exam_subject.question_count
        # If there are foreign language subjects and all were skipped, set total score to 0
        if has_foreign_language_subjects and all_foreign_language_skipped:
            self.errors.append(
                f"Tələbə {student_data['work_number']} {student_data['student_name']}  ({student_data['contact_number']}) bütün xarici dil fənlərini keçdi. Xarici dil boş qaldı."
            )
        return total_score, subject_results

    def _is_matching_foreign_language(self, subject_name: str, student_language: str) -> bool:
        """
        Check if the student's selected foreign language matches the current subject
        Maps common foreign language codes to subject names
        """
        # Define mapping between student language codes and subject names
        language_mapping = {
            'I': ['İngilis dili', 'English', 'İngiliscə'],
            'R': ['Rus dili', 'Russian', 'Rusca'],
            'F': ['Fransız dili', 'French', 'Fransızca'],
            'A': ['Alman dili', 'German', 'Almanca'],
            'E': ['İngilis dili', 'English', 'İngiliscə'],  # Alternative English code
        }
        
        student_language_upper = student_language.upper()
        subject_name_lower = subject_name.lower()
        
        # If student language is a single character (code), use mapping
        if len(student_language_upper) == 1 and student_language_upper in language_mapping:
            possible_subjects = language_mapping[student_language_upper]
            return any(subj.lower() in subject_name_lower for subj in possible_subjects)
        
        # If student language is a full name, check if it matches subject name
        return student_language.lower() in subject_name_lower or subject_name_lower in student_language.lower()

    def _get_answers_key(self, student_data: Dict) -> str:
        """Generate key for correct answers lookup"""
        section = Section.objects.get(name__startswith=student_data['section'])
        key = f"{section.name[0]}_{student_data['variant']}"
        
        if 'class_level' in student_data:
            key = f"{student_data['class_level']}_" + key
        if 'group' in student_data:
            key = f"{student_data['group']}_" + key 
        if 'category' in student_data:
            key = f"{student_data['category']}_" + key
            
        return key

    def _calculate_question_score(self, student_answer: str, correct_data: Dict) -> Decimal:
        """Calculate score for individual question based on question type"""
        student_answer_cop = student_answer
        student_answer = student_answer
        correct_answer = correct_data['correct_answer']
        base_score = Decimal(str(correct_data['score']))
        penalty_score = Decimal(str(correct_data['penalty_score']))
        question_type = correct_data.get('question_type', 'closed')
        
        # Check for * symbol (except for multiple choice questions)
        if '*' in student_answer and not question_type in ['true_false']:
            return Decimal('0') - penalty_score
        
        # Determine question type and calculate score
        if correct_data.get('is_starred', False):
            return base_score
        elif question_type  == 'close':
            return self._calculate_closed_question_score(student_answer, correct_answer, base_score, penalty_score)
        elif question_type == 'open_coded' and correct_data.get('is_multiple_choice', False):
            return self._calculate_multiple_choice_score(student_answer, correct_answer, base_score, penalty_score)
        elif question_type == 'open_coded' and not correct_data.get('is_multiple_choice', False):
            return self._calculate_open_question_score(student_answer, correct_answer, base_score, penalty_score)
        elif question_type == 'open':
            return self._calculate_explained_open_score(student_answer, correct_answer, base_score)
        elif question_type == 'true_false':
            return self._calculate_multiple_alphabet_choice_score(student_answer, correct_answer, base_score, penalty_score)
        elif question_type == 'essay':
            return self._calculate_essay_question_score(student_answer, correct_answer, base_score, penalty_score)
        elif question_type == 'matching':
            return self._calculate_choice_question_score(student_answer, correct_answer, base_score, penalty_score)
        else:
            # Default case - treat as closed question
            return self._calculate_closed_question_score(student_answer, correct_answer, base_score, penalty_score)

    def _calculate_closed_question_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for closed questions (A,B,C,D,E)"""
        if student_answer.upper() == correct_answer.upper():
            return base_score
        elif student_answer.strip():
            return Decimal('0') - penalty_score
        else:
            return Decimal('0')
    def _calculate_essay_question_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for essay questions (e.g., 134,21)"""
        student_answer = student_answer.strip()
        correct_answer = correct_answer.strip()
        
        try:
            if student_answer:
                # Convert student answer to decimal and multiply by base score
                return Decimal(str(float(student_answer))) * base_score
            else:
                return Decimal('0')
        except (ValueError, TypeError):
            return Decimal('0')

    def _calculate_open_question_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for open questions (134,21)"""
        student_answer = student_answer.strip()
        if student_answer == correct_answer:
            return base_score
        elif student_answer:
            return Decimal('0') - penalty_score
        else:
            return Decimal('0')

    def _calculate_explained_open_score(self, student_answer: str, correct_answer: str, base_score: Decimal) -> Decimal:
        """Calculate score for explained open questions (1,1/3,2/3,1/2,0)"""
        student_answer = student_answer.strip()
        
        # Parse fraction or decimal
        try:
            if '/' in student_answer:
                parts = student_answer.split('/')
                answer_value = Decimal(parts[0]) / Decimal(parts[1])
            else:
                answer_value = Decimal(student_answer)
            
            return base_score * answer_value
        except:
            return Decimal('0')

    def _calculate_choice_question_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for choice questions (1-ac,2-bd,3-e)"""
        # Parse student answer from 15-character format
        parsed_student = self._parse_choice_answer(student_answer)
        correct_choices = correct_answer.split(';')
        
        if parsed_student == correct_choices:
            return base_score
        elif any(parsed_student):
            return Decimal('0') - penalty_score
        else:
            return Decimal('0')

    def _parse_choice_answer(self, answer: str) -> List[str]:
        """Parse choice answer from 15-character format"""
        if len(answer) != 15:
            return []
        
        choices = []
        for i in range(0, 15, 5):
            choice = answer[i:i+5].strip()
            choices.append(choice.lower())
        
        return choices

    def _calculate_multiple_choice_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for multiple choice questions (e.g., 134, student selects first, third, and fourth answers)"""
        student_choices = sorted(student_answer.strip())
        correct_choices = sorted(correct_answer.strip())
        
        if student_choices == correct_choices:
            return base_score

        return Decimal('0') - penalty_score

    def _calculate_multiple_alphabet_choice_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for multiple alphabet choice questions (e.g., ABAB)"""
        student_choices = set(student_answer.strip().upper())
        correct_choices = set(correct_answer.strip().upper())

        # Count how many student choices are in the correct choices
        intersection_count = len(student_choices & correct_choices)

        if student_choices == correct_choices:
            return base_score
        elif intersection_count == 3:
            return Decimal('0.5')
        else:
            return Decimal('0')

