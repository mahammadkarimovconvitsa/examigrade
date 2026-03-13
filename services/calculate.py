# services/txt_import_service.py
import re
from typing import List, Dict, Tuple, Optional
from decimal import Decimal , ROUND_HALF_UP
from venv import logger
from examadmin.models import Exam,Class,NotUploadedStudentResult, StudentResult, SubjectResult, CorrectAnswerCombination, CorrectAnswer, Branch, Section, Subject, Group
from examadmin.models import ImportLog
import random
import json

class TxtImportService:
    """
    Service for importing student results from TXT files
    Handles different exam types with specific data structures and scoring formulas
    """
    
    EXAM_TYPE_PARSERS = {
        '9-cu sinif buraxılış': 'parse_9th_grade',
        '10-cu sinif buraxılış': 'parse_10th_grade',
        '11-ci sinif buraxılış': 'parse_11th_grade', 
        'Blok imtahanı': 'parse_block_exam',
        'Dövlət Qulluğu': 'parse_government_service',
        'Magistratura': 'parse_magistr_service',
        'Bilik yarışı': 'parse_magistr_with_class',
        'Təkmilləşdirmə': 'parse_magistr_with_class',
        'Müəllimlərin İşə Qəbulu': 'parse_magistr_service',
        'Sertifikasiya': 'parse_magistr_service',
        'Azərbaycan dili (dövlət dili kimi)': 'parse_11th_grade_without_foreign_language',
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
                key = f"{combination.class_level.id}_" + key
            if combination.group_name:
                key = f"{combination.group_name}_" + key
            if combination.category:
                key = f"{combination.category}_" + key
                
            answers[key] = {}
            # Use direct query instead of related manager
            correct_answers_qs = CorrectAnswer.objects.filter(combination=combination)
            logger.debug(f"Loading correct answers for key: {key}, Count: {correct_answers_qs.count()}")
            
            for ca in correct_answers_qs:
                answers[key][str(ca.question_number)+'-'+str(ca.subject.id)] = {
                    'question_number': ca.question_number,
                    'correct_answer': ca.correct_answer,
                    'question_type': ca.question_type,
                    'is_starred': ca.is_starred,
                    'score': ca.score,
                    'penalty_score':ca.penalty_score,
                    'is_multiple_choice': ca.is_multiple_choice,
                    'subject':ca.subject,
                }
        
        return answers

    def import_from_txt(self, file_content: str) -> Dict:
        """Main import method"""
        try:
            lines = file_content.split('\n')
        except Exception as e:
            self.errors.append(f"Fayl məzmunu oxuna bilmədi: {str(e)}")
            return {
                'success': False,
                'imported_count': 0,
                'errors': self.errors,
                'results': []
            }
        
        results = []
        
        for line_num, line in enumerate(lines, 1):
            try:
                if not line.strip():
                    continue
                    
                student_data = None
                try:
                    student_data = self._parse_line(line.strip())
                    if not student_data:
                        self.errors.append(f"Sətir {line_num}: Məlumatlar analiz edilə bilmədi - sətir keçildi")
                        continue
                        
                    try:
                        student_result = self._create_student_result(student_data)
                        if student_result:  # Only append if creation was successful
                            results.append(student_result)
                            self.imported_count += 1
                        else:
                            self.errors.append(f"Sətir {line_num}, İş nömrəsi {student_data.get('work_number', 'N/A')}: Tələbə nəticəsi yaradıla bilmədi")
                    except Exception as create_error:
                        self.errors.append(f"Sətir {line_num}, İş nömrəsi {student_data.get('work_number', 'N/A')}: Tələbə nəticəsi yaradılarkən xəta - {str(create_error)}")
                        # Try to create NotUploadedStudentResult even with critical errors
                        try:
                            if student_data and student_data.get('student_name') and student_data.get('work_number'):
                                NotUploadedStudentResult.objects.create(
                                    exam=self.exam,
                                    student_name=student_data.get('student_name'),
                                    work_number=student_data.get('work_number')
                                )
                                self.errors.append(f"Sətir {line_num}: Tələbə NotUploadedStudentResult kimi qeydə alındı")
                        except Exception as db_error:
                            self.errors.append(f"Sətir {line_num}: NotUploadedStudentResult yaradılarkən DB xətası - {str(db_error)}")
                        # Continue processing even after critical errors
                        continue
                            
                except Exception as parse_error:
                    # Critical parsing error - try to extract at least basic info and continue
                    self.errors.append(f"Sətir {line_num}: Kritik analiz xətası - {str(parse_error)} - sətir keçildi, emal davam edir")
                    
                    # Try to extract basic student info even from malformed line
                    try:
                        basic_parts = line.strip().split(';')
                        if len(basic_parts) >= 5:  # At least have basic fields
                            try:
                                basic_student_name = f"{basic_parts[0].strip()} {basic_parts[1].strip()}" if len(basic_parts) > 1 else basic_parts[0].strip()
                                basic_work_number = basic_parts[4].strip() if len(basic_parts) > 4 else f"ERROR_{line_num}"
                                
                                NotUploadedStudentResult.objects.create(
                                    exam=self.exam,
                                    student_name=basic_student_name[:100],  # Limit length
                                    work_number=basic_work_number[:20]  # Limit length
                                )
                                self.errors.append(f"Sətir {line_num}: Kritik xəta olmasına rağmən tələbə məlumatları qeydə alındı: {basic_student_name}")
                            except Exception as basic_extract_error:
                                self.errors.append(f"Sətir {line_num}: Hətta əsas məlumatlar çıxarıla bilmədi - {str(basic_extract_error)}")
                    except Exception as basic_parse_error:
                        self.errors.append(f"Sətir {line_num}: Tamamilə analiz edilə bilmədi - {str(basic_parse_error)}")
                    
                    continue  # Always continue processing
                    
            except Exception as line_error:
                self.errors.append(f"Sətir {line_num}: Ümumi sətir emal xətası - {str(line_error)}")
                continue
        
        # Create import log - continue even if this fails
        try:
            ImportLog.objects.create(
                exam=self.exam,
                branch=self.branch,
                import_type='results',
                file_name=f'imported_results_{self.exam.name}_{self.branch.name}.txt',
                file_size=len(file_content) if file_content else 0,
                records_imported=self.imported_count,
                errors=self.errors,
            )
        except Exception as log_error:
            self.errors.append(f"Import log xətası: {str(log_error)} - import davam etdi")
            
        # Update participant count - continue even if this fails
        try:
            part_count = StudentResult.objects.filter(exam=self.exam).count()
            self.exam.participant_count = part_count
            self.exam.save()
        except Exception as count_error:
            self.errors.append(f"İştirakçı sayı yenilənərkən xəta: {str(count_error)} - import tamamlandı")
            
        return {
            'success': True,
            'imported_count': self.imported_count,
            'errors': self.errors,
            'results': results
        }




    def _parse_line(self, line: str) -> Optional[Dict]:
        """Parse line based on exam type"""
        try:
            if not line or not line.strip():
                return None
                
            parser_method = self.EXAM_TYPE_PARSERS.get(self.exam.type)
            
            # If exam type is not in the predefined parsers, use magistr_service as default
            if not parser_method:
                # Check if exam type includes class data
                exam_types_with_class = ['Bilik yarışı', 'Təkmilləşdirmə']
                
                if self.exam.type in exam_types_with_class:
                    parser_method = 'parse_magistr_with_class'
                else:
                    parser_method = 'parse_magistr_service'
            
            try:
                parser_func = getattr(self, parser_method)
                return parser_func(line)
            except AttributeError:
                # If parser method doesn't exist, try fallback parsing
                try:
                    return self._parse_fallback(line)
                except Exception as fallback_error:
                    raise ValueError(f"Parser metodu tapılmadı və fallback də uğursuz: {parser_method} - {str(fallback_error)}")
            except Exception as parse_error:
                # If specific parser fails, try fallback parsing
                try:
                    fallback_result = self._parse_fallback(line)
                    if fallback_result:
                        return fallback_result
                except Exception:
                    pass
                raise ValueError(f"Sətir analiz edilərkən xəta ({parser_method}): {str(parse_error)}")
                
        except Exception as e:
            # Last resort - try basic parsing
            try:
                return self._parse_basic(line)
            except Exception as basic_error:
                raise ValueError(f"Sətir emal edilərkən ümumi xəta: {str(e)} - Basic parsing də uğursuz: {str(basic_error)}")

    def parse_9th_grade(self, line: str) -> Dict:
        """
        Parse 9th grade graduation exam data
        Format: "ABCCD;ABCCDEe *i;0123456789;K;012345;A;B;8;078;R;..."
        """
        try:
            parts = line.split(';')
            if len(parts) < 10:
                raise ValueError("9-cu sinif məlumatları natamam")
                
            try:
                # Replace specific characters in student name
                parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
                parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
            except Exception as name_error:
                # If name processing fails, use original parts
                pass
            
            # Extract and process class_level
            class_level = parts[7].strip() if len(parts) > 7 else ''
            # Check if class level is "M " (graduate)
            if class_level.upper() == "M" or class_level.upper() == "M ":
                class_level = "Məzun"
            
            return {
                'student_name': f"{parts[0].strip()} {parts[1].strip()}",
                'contact_number': parts[2].strip() if len(parts) > 2 else '',
                'gender': parts[3].strip() if len(parts) > 3 else 'K',
                'work_number': parts[4].strip() if len(parts) > 4 else '',
                'section': parts[5].strip() if len(parts) > 5 else '',
                'variant': parts[6].strip() if len(parts) > 6 else '',
                'class_level': class_level,
                'school_number': parts[8].strip() if len(parts) > 8 else '',
                'foreign_language': parts[9].strip() if len(parts) > 9 else '',
                'answers': parts[10:] if len(parts) > 10 else []
            }
        except Exception as e:
            raise ValueError(f"9-cu sinif məlumatları analiz edilərkən xəta: {str(e)}")

    def parse_10th_grade(self, line: str) -> Dict:
        """
        Parse 10th grade graduation exam data
        Format: "AYTeN;ABBASOVA;0775821888;Q;102124;A;A;10;056;I;..."
        """
        try:
            parts = line.split(';')
            if len(parts) < 10:
                raise ValueError("10-cu sinif məlumatları natamam")
                
            try:
                parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
                parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
            except Exception:
                # If name processing fails, continue with original parts
                pass
            
            # Safe extraction with bounds checking
            class_level = '10'  # Default
            try:
                if len(parts) > 7 and parts[7].strip():
                    raw_class_level = parts[7].strip()
                    # Check if class level is "M " (graduate)
                    if raw_class_level.upper() == "M" or raw_class_level.upper() == "M ":
                        class_level = "Məzun"
                    elif raw_class_level.isdigit():
                        class_level = raw_class_level
                    else:
                        class_level = raw_class_level
            except Exception:
                pass
            
            return {
                'student_name': f"{parts[0].strip()} {parts[1].strip()}",
                'contact_number': parts[2].strip() if len(parts) > 2 else '',
                'work_number': parts[4].strip() if len(parts) > 4 else '',
                'gender': parts[3].strip() if len(parts) > 3 else 'K',
                'section': parts[5].strip() if len(parts) > 5 else '',
                'variant': parts[6].strip() if len(parts) > 6 else '',
                'class_level': class_level,
                'school_number': parts[8].strip() if len(parts) > 8 else '',
                'foreign_language': parts[9].strip() if len(parts) > 9 else '',
                'foreign_subject': parts[9].strip() if len(parts) > 9 else '',
                'answers': parts[10:] if len(parts) > 10 else []
            }
        except Exception as e:
            raise ValueError(f"10-cu sinif məlumatları analiz edilərkən xəta: {str(e)}")

    def parse_11th_grade(self, line: str) -> Dict:
        """
        Parse 11th grade graduation exam data
        Format: "AYTeN;ABBASOVA;0775821888;Q;102124;A;A;11;056;I;..."
        """
        try:
            parts = line.split(';')
            if len(parts) < 10:
                raise ValueError("11-ci sinif məlumatları natamam")
                
            try:
                parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
                parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
            except Exception:
                # If name processing fails, continue with original parts
                pass
            
            # Safe extraction with bounds checking
            class_level = '11'  # Default
            try:
                if len(parts) > 7 and parts[7].strip():
                    raw_class_level = parts[7].strip()
                    # Check if class level is "M " (graduate)
                    if raw_class_level.upper() == "M" or raw_class_level.upper() == "M ":
                        class_level = "Məzun"
                    elif raw_class_level.isdigit():
                        class_level = raw_class_level
                    else:
                        class_level = raw_class_level
            except Exception:
                pass
            
            return {
                'student_name': f"{parts[0].strip()} {parts[1].strip()}",
                'contact_number': parts[2].strip() if len(parts) > 2 else '',
                'work_number': parts[4].strip() if len(parts) > 4 else '',
                'gender': parts[3].strip() if len(parts) > 3 else 'K',
                'section': parts[5].strip() if len(parts) > 5 else '',
                'variant': parts[6].strip() if len(parts) > 6 else '',
                'class_level': class_level,
                'school_number': parts[8].strip() if len(parts) > 8 else '',
                'foreign_language': parts[9].strip() if len(parts) > 9 else '',
                'foreign_subject': parts[9].strip() if len(parts) > 9 else '',
                'answers': parts[10:] if len(parts) > 10 else []
            }
        except Exception as e:
            raise ValueError(f"11-ci sinif məlumatları analiz edilərkən xəta: {str(e)}")
    def parse_11th_grade_without_foreign_language(self, line: str) -> Dict:
        """
        Parse 11th grade graduation exam data
        Format: "AYTeN;ABBASOVA;0775821888;Q;102124;A;A;11;056;I;..."
        """
        try:
            parts = line.split(';')
            if len(parts) < 8:
                raise ValueError("11-ci sinif məlumatları natamam (xarici dil olmadan)")
                
            try:
                parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
                parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
            except Exception:
                pass
            
            # Safe class level extraction
            class_level = '11'  # Default
            try:
                if len(parts) > 7 and parts[7].strip():
                    raw_class_level = parts[7].strip()
                    # Check if class level is "M " (graduate)
                    if raw_class_level.upper() == "M" or raw_class_level.upper() == "M ":
                        class_level = "Məzun"
                    elif raw_class_level.isdigit():
                        class_level = raw_class_level
                    else:
                        class_level = raw_class_level
            except Exception:
                pass
            
            return {
                'student_name': f"{parts[0].strip()} {parts[1].strip()}",
                'contact_number': parts[2].strip() if len(parts) > 2 else '',
                'work_number': parts[4].strip() if len(parts) > 4 else '',
                'gender': parts[3].strip() if len(parts) > 3 else 'K',
                'section': parts[5].strip() if len(parts) > 5 else '',
                'variant': parts[6].strip() if len(parts) > 6 else '',
                'class_level': class_level,
                'school_number': '',  # Will be mapped later
                'answers': parts[8:] if len(parts) > 8 else []
            }
        except Exception as e:
            raise ValueError(f"11-ci sinif məlumatları analiz edilərkən xəta (xarici dil olmadan): {str(e)}")

    def parse_block_exam(self, line: str) -> Dict:
        """
        Parse block exam data
        Format: "ABCCDEeFGg;ACDeGHIJQLNO;0123456789;K;012345;R;B;M;1RI;..."
        """
        try:
            parts = line.split(';')

            if len(parts) < 9:
                raise ValueError("Blok imtahanı məlumatları natamam")
                
            # Group mapping with error handling
            group = "Naməlum qrup"  # Default
            try:
                group_raw = parts[8].strip() if len(parts) > 8 else ""
                if group_raw == "1RI":
                    group = "Rİ altqrupu"
                elif group_raw == "1RK":
                    group = "RK altqrupu"
                elif group_raw == "2":
                    group = "2-ci qrup"
                elif group_raw == "3DT":
                    group = "DT altqrupu"
                elif group_raw == "3TC":
                    group = "TC altqrupu"
                elif group_raw == "4":
                    group = "4-cü qrup"
                elif group_raw:
                    group = group_raw  # Use original if not in mapping
            except Exception:
                pass
            
            try:
                parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
                parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
            except Exception:
                pass
            
            # Extract and process class_level
            class_level = parts[7].strip() if len(parts) > 7 else ''
            # Check if class level is "M " (graduate)
            if class_level.upper() == "M" or class_level.upper() == "M ":
                class_level = "Məzun"
            
            return {
                'student_name': f"{parts[0].strip()} {parts[1].strip()}",
                'contact_number': parts[2].strip() if len(parts) > 2 else '',
                'work_number': parts[4].strip() if len(parts) > 4 else '',
                'section': parts[5].strip() if len(parts) > 5 else '',
                'variant': parts[6].strip() if len(parts) > 6 else '',
                'class_level': class_level,
                'gender': parts[3].strip() if len(parts) > 3 else 'K',
                'group': group,
                'school_number': '',  # Will be mapped later
                'answers': parts[9:] if len(parts) > 9 else []
            }
        except Exception as e:
            raise ValueError(f"Blok imtahanı məlumatları analiz edilərkən xəta: {str(e)}")

    def parse_government_service(self, line: str) -> Dict:
        """
        Parse government service exam data
        Format: "PeRViZ;BiLisZADe;0707163550;K;123456;A;C;BA;..."
        """
        try:
            parts = line.split(';')
            if len(parts) < 8:
                raise ValueError("Dövlət qulluğu məlumatları natamam")
                
            try:
                parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
                parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
            except Exception:
                pass
            
            return {
                'student_name': f"{parts[0].strip()} {parts[1].strip()}",
                'contact_number': parts[2].strip() if len(parts) > 2 else '',
                'work_number': parts[4].strip() if len(parts) > 4 else '',
                'section': parts[5].strip() if len(parts) > 5 else '',
                'variant': parts[6].strip() if len(parts) > 6 else '',
                'category': parts[7].strip() if len(parts) > 7 else '',
                'gender': parts[3].strip() if len(parts) > 3 else 'K',
                'school_number': '',  # Will be mapped later
                'answers': parts[8:] if len(parts) > 8 else []
            }
        except Exception as e:
            raise ValueError(f"Dövlət qulluğu məlumatları analiz edilərkən xəta: {str(e)}")

    def parse_magistr_service(self, line: str) -> Dict:
        """
        Parse magistr/default exam data (without class level)
        Format: "PeRViZ;BiLisZADe;0707163550;K;123456;A;B;F;..."
        """
        try:
            parts = line.split(';')
            if len(parts) < 8:
                raise ValueError("Magistr məlumatları natamam")
                
            try:
                parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
                parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
            except Exception:
                pass
                
            data = {
                'student_name': f"{parts[0].strip()} {parts[1].strip()}",
                'contact_number': parts[2].strip() if len(parts) > 2 else '',
                'work_number': parts[4].strip() if len(parts) > 4 else '',
                'gender': parts[3].strip() if len(parts) > 3 else 'K',
                'school_number': '',  # Will be mapped later
            }
            
            try:
                if self.exam.type in ['Magistratura']:
                    data['foreign_language'] = parts[7].strip() if len(parts) > 7 else ''
                    data['foreign_subject'] = parts[7].strip() if len(parts) > 7 else ''
                    data['answers'] = parts[8:] if len(parts) > 8 else []
                    data['section'] = parts[5].strip() if len(parts) > 5 else ''
                    data['variant'] = parts[6].strip() if len(parts) > 6 else ''
                else:
                    data['answers'] = parts[11:] if len(parts) > 11 else []
                    data['section'] = parts[6].strip() if len(parts) > 6 else ''
                    data['variant'] = parts[7].strip() if len(parts) > 7 else ''
            except Exception as type_error:
                # Fallback to basic magistratura format if type-specific parsing fails
                data['answers'] = parts[8:] if len(parts) > 8 else []
                data['section'] = parts[5].strip() if len(parts) > 5 else ''
                data['variant'] = parts[6].strip() if len(parts) > 6 else ''
                
            return data
        except Exception as e:
            raise ValueError(f"Magistr məlumatları analiz edilərkən xəta: {str(e)}")

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
        FiDAN     ;MuRSeLZADe  ;0705660311;Q;600014;07;A;A; ;I;30 
        
        """
        try:
            parts = line.split(';')
            if len(parts) < 11:
                raise ValueError("Sinif məlumatları ilə imtahan məlumatları natamam")
            
            try:
                # Replace specific characters in student name parts
                parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
                parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
            except Exception:
                pass
            
            # Extract contact number with error handling - clean it from any special characters
            contact_number = ''
            try:
                contact_number = parts[2].strip().replace('*', '').replace(' ', '') if len(parts) > 2 else ''
            except Exception:
                pass
            
            # Extract class level safely
            class_level = ''
            try:
                if len(parts) > 5 and parts[5].strip():
                    raw_class_level = parts[5].strip()
                    # Check if class level is "M " (graduate)
                    if raw_class_level.upper() == "M" or raw_class_level.upper() == "M ":
                        class_level = "Məzun"
                    else:
                        class_level = str(int(raw_class_level)).strip()
            except (ValueError, IndexError):
                raw_class_level = parts[5].strip() if len(parts) > 5 else ''
                # Check if class level is "M " (graduate) in fallback case too
                if raw_class_level.upper() == "M" or raw_class_level.upper() == "M ":
                    class_level = "Məzun"
                else:
                    class_level = raw_class_level
            
            return {
                'student_name': f"{parts[0].strip()} {parts[1].strip()}",
                'contact_number': contact_number,
                'school_number': parts[10].strip() if len(parts) > 10 else '',  # Məktəb nömrəsi
                'work_number': parts[4].strip() if len(parts) > 4 else '',
                'class_level': class_level,  # Sinif
                'gender': parts[3].strip() if len(parts) > 3 else 'K',  # Cinsi (Q/K)
                'section': parts[6].strip() if len(parts) > 6 else '',
                'variant': parts[7].strip() if len(parts) > 7 else '',
                'foreign_language': parts[9].strip() if len(parts) > 9 else '',
                'foreign_subject': parts[9].strip() if len(parts) > 9 else '',
                'answers': parts[11:] if len(parts) > 11 else []
            }
        except Exception as e:
            raise ValueError(f"Sinif məlumatları ilə imtahan məlumatları analiz edilərkən xəta: {str(e)}")

    def _create_student_result(self, student_data: Dict) -> Optional[StudentResult]:
        """Create student result with calculated scores"""
        # Get section object with error handling - if not found, create student with null scores
        section = None
        section_found = True
        try:
            if student_data.get('section'):
                section = Section.objects.filter(name__startswith=student_data['section']).first()
            if not section:
                # Mark that section was not found, but continue creating the student
                section_found = False
                self.errors.append(f"Bölmə tapılmadı: {student_data.get('section', 'N/A')}. Tələbə null ballarla yaradılacaq.")
        except Exception as section_error:
            section_found = False
            self.errors.append(f"Bölmə axtarılarkən xəta: {str(section_error)}. Tələbə null ballarla yaradılacaq.")

        # Work number validation and correction with error handling
        try:
            # Check if work_number is empty or invalid
            if not student_data.get('work_number') or not re.match(r'^\d{0,9}$', student_data['work_number']):
                # Only extract numeric digits from the work number if it exists
                try:
                    new_work_number = ''.join(c for c in student_data.get('work_number', '') if c.isdigit())
                except Exception:
                    new_work_number = ''
                
                # If no digits were found or work_number was empty, generate a random 6-digit number
                if not new_work_number:
                    try:
                        new_work_number = ''.join(random.choices('0123456789', k=6))
                    except Exception:
                        new_work_number = '123456'  # Fallback work number
                
                # Log the change
                try:
                    if not student_data.get('work_number'):
                        self.errors.append(f"İş nömrəsi boş idi. Yeni təsadüfi iş nömrəsi yaradıldı: {new_work_number}")
                    else:
                        self.errors.append(f"{student_data['work_number']} iş nömrəsi yalnış formatdadır. İş nömrəsi dəyişdirildi: {new_work_number}")
                except Exception:
                    pass
                
                student_data['work_number'] = new_work_number
        except Exception as work_number_error:
            # If work number processing completely fails, generate a fallback
            try:
                fallback_number = ''.join(random.choices('0123456789', k=6))
                student_data['work_number'] = fallback_number
                self.errors.append(f"İş nömrəsi emal edilərkən xəta baş verdi. Təsadüfi nömrə yaradıldı: {fallback_number}")
            except Exception:
                student_data['work_number'] = '999999'
                self.errors.append(f"İş nömrəsi emal xətası. Default nömrə istifadə edildi: 999999")


        # Check for existing student by work number with error handling
        existing_student = None
        existing_subject_results = None
        try:
            existing_student = StudentResult.objects.filter(
                exam=self.exam,
                work_number=student_data['work_number']
            ).first()
            existing_subject_results = SubjectResult.objects.filter(
                student_result__exam=self.exam,
                student_result__work_number=student_data['work_number']
            )
        except Exception as db_check_error:
            self.errors.append(f"Mövcud tələbə yoxlanılarkən DB xətası: {str(db_check_error)}")
            # Continue with creation assuming no existing student

        # Student creation logic with comprehensive error handling
        student_result = None
        try:
            # Helper function to safely get database objects
            def get_class_object(class_name):
                try:
                    if class_name:
                        return Class.objects.filter(name=class_name).first()
                except Exception:
                    pass
                return None
                
            def get_group_object(group_name):
                try:
                    if group_name:
                        return Group.objects.filter(name=group_name).first()
                except Exception:
                    pass
                return None
            
            # Case 1: Existing student with results, no recheck
            if existing_student and existing_subject_results and existing_subject_results.exists() and not self.recheck:
                try:
                    # Generate a random digit number with the same length as the existing work number
                    new_work_number = ''.join(random.choices('0123456789', k=len(student_data['work_number'])))
                    student_data['work_number'] = new_work_number
                    self.errors.append(
                        f"{existing_student.work_number} iş nömrəli tələbə mövcuddur: {existing_student.student_name} ({existing_student.contact_number}). "
                        f"Yeni tələbə {student_data['student_name']} {student_data['contact_number']} İş nömrəsi dəyişdirildi: {new_work_number}"
                    )
                except Exception as duplicate_error:
                    self.errors.append(f"Dublikat iş nömrəsi həll edilərkən xəta: {str(duplicate_error)}")
                    
                try:
                    student_result = StudentResult.objects.create(
                        exam=self.exam,
                        student_name=student_data.get('student_name', ''),
                        work_number=student_data.get('work_number', ''),
                        gender=student_data.get('gender', 'K'),
                        contact_number=student_data.get('contact_number', ''),
                        school_number=student_data.get('school_number', ''),
                        branch=self.branch,
                        variant=student_data.get('variant', ''),
                        class_level=get_class_object(student_data.get('class_level')),
                        section=section,
                        group=get_group_object(student_data.get('group')),
                        is_active=True,
                        original_answers=json.dumps(student_data.get('answers', []), ensure_ascii=False)
                    )
                except Exception as create_error:
                    raise ValueError(f"Yeni tələbə yaradılarkən xəta (case 1): {str(create_error)}")
          
            # Case 2: Existing student without results, no recheck
            elif existing_student and existing_subject_results and not existing_subject_results.exists() and not self.recheck:
                try:
                    # Generate a random digit number with the same length as the existing work number
                    new_work_number = ''.join(random.choices('0123456789', k=len(student_data['work_number'])))
                    student_data['work_number'] = new_work_number
                    self.errors.append(
                        f"{existing_student.work_number} iş nömrəli tələbə mövcuddur: {existing_student.student_name} ({existing_student.contact_number}). "
                        f"Yeni tələbə {student_data['student_name']} {student_data['contact_number']} İş nömrəsi dəyişdirildi: {new_work_number}"
                    )
                    student_result = StudentResult.objects.create(
                        exam=self.exam,
                        student_name=student_data.get('student_name', ''),
                        work_number=student_data.get('work_number', ''),
                        gender=student_data.get('gender', 'K'),
                        contact_number=student_data.get('contact_number', ''),
                        school_number=student_data.get('school_number', ''),
                        branch=self.branch,
                        variant=student_data.get('variant', ''),
                        class_level=get_class_object(student_data.get('class_level')),
                        section=section,
                        group=get_group_object(student_data.get('group')),
                        is_active=True,
                        original_answers=json.dumps(student_data.get('answers', []), ensure_ascii=False)
                    )
                except Exception as create_error:
                    raise ValueError(f"Tələbə yaradılarkən xəta (case 2): {str(create_error)}")

            # Case 3: Existing student without results, with recheck
            elif existing_student and existing_subject_results and not existing_subject_results.exists() and self.recheck:
                try:
                    student_result = StudentResult.objects.get(
                        exam=self.exam,
                        work_number=student_data['work_number'],
                    )
                    student_result.section = section
                    student_result.student_name = student_data.get('student_name', student_result.student_name)
                    student_result.contact_number = student_data.get('contact_number', student_result.contact_number)
                    student_result.school_number = student_data.get('school_number', student_result.school_number)
                    student_result.gender = student_data.get('gender', student_result.gender)
                    student_result.branch = self.branch
                    student_result.variant = student_data.get('variant', student_result.variant)
                    student_result.class_level = get_class_object(student_data.get('class_level'))
                    student_result.group = get_group_object(student_data.get('group'))
                    student_result.is_active = True
                    student_result.original_answers = json.dumps(student_data.get('answers', []), ensure_ascii=False)
                except Exception as update_error:
                    raise ValueError(f"Mövcud tələbə yenilənərkən xəta (case 3): {str(update_error)}")

            # Case 4: Existing student with results, with recheck
            elif existing_student and existing_subject_results and existing_subject_results.exists() and self.recheck:
                try:
                    existing_subject_results.delete()
                    student_result = StudentResult.objects.get(
                        exam=self.exam,
                        work_number=student_data['work_number'],
                    )
                    student_result.section = section
                    student_result.student_name = student_data.get('student_name', student_result.student_name)
                    student_result.contact_number = student_data.get('contact_number', student_result.contact_number)
                    student_result.school_number = student_data.get('school_number', student_result.school_number)
                    student_result.gender = student_data.get('gender', student_result.gender)
                    student_result.branch = self.branch
                    student_result.variant = student_data.get('variant', student_result.variant)
                    student_result.class_level = get_class_object(student_data.get('class_level'))
                    student_result.group = get_group_object(student_data.get('group'))
                    student_result.is_active = True
                    student_result.original_answers = json.dumps(student_data.get('answers', []), ensure_ascii=False)
                except Exception as recheck_error:
                    raise ValueError(f"Recheck zamanı mövcud tələbə yenilənərkən xəta: {str(recheck_error)}")
                
            # Case 5: New student
            else:
                try:
                    student_result = StudentResult.objects.create(
                        exam=self.exam,
                        student_name=student_data.get('student_name', ''),
                        work_number=student_data.get('work_number', ''),
                        gender=student_data.get('gender', 'K'),
                        contact_number=student_data.get('contact_number', ''),
                        school_number=student_data.get('school_number', ''),
                        branch=self.branch,
                        variant=student_data.get('variant', ''),
                        class_level=get_class_object(student_data.get('class_level')),
                        section=section,
                        group=get_group_object(student_data.get('group')),
                        is_active=True,
                        original_answers=json.dumps(student_data.get('answers', []), ensure_ascii=False)
                    )
                except Exception as new_create_error:
                    raise ValueError(f"Yeni tələbə yaradılarkən xəta: {str(new_create_error)}")
                    
        except Exception as student_creation_error:
            # Even if student creation fails, try to create a minimal record
            try:
                self.errors.append(f"Tələbə yaradılması/yenilənməsi zamanı ümumi xəta: {str(student_creation_error)}")
                # Try to create minimal student record
                try:
                    student_result = StudentResult.objects.create(
                        exam=self.exam,
                        student_name=student_data.get('student_name', 'Xətalı Tələbə')[:100],
                        work_number=student_data.get('work_number', f"ERROR_{abs(hash(str(student_data))) % 999999}")[:20],
                        gender=student_data.get('gender', 'K'),
                        contact_number=student_data.get('contact_number', '')[:20],
                        school_number=student_data.get('school_number', '')[:50],
                        branch=self.branch,
                        variant=student_data.get('variant', 'A')[:10],
                        class_level=None,  # Set to None if can't determine
                        section=None,      # Set to None if can't determine
                        group=None,        # Set to None if can't determine
                        is_active=False,   # Mark as inactive due to errors
                        total_score=None,  # Null score due to errors
                        original_answers=json.dumps([], ensure_ascii=False)
                    )
                    self.errors.append(f"Minimal tələbə nəticəsi yaradıldı (xətalı data ilə): {student_result.student_name}")
                except Exception as minimal_create_error:
                    self.errors.append(f"Minimal tələbə nəticəsi də yaradıla bilmədi: {str(minimal_create_error)}")
                    return None
            except Exception:
                return None
                
        # Check if a student with the same name and contact number exists
        # Calculate scores with comprehensive error handling
        total_score = None
        subject_results = []
        additional_data = []
        
        # Only calculate scores if section was found
        if section_found:
            try:
                total_score, subject_results, additional_data = self._calculate_scores(student_data)
            except Exception as score_calc_error:
                self.errors.append(f"İş nömrəsi {student_data.get('work_number', 'N/A')}: Bal hesablanarkən kritik xəta - {str(score_calc_error)} - tələbə null ballarla yaradılacaq")
                # Set scores to null but still create the student
                total_score = None
                subject_results = []
                # Try to get at least basic subject structure for logging
                try:
                    section_obj = Section.objects.filter(name__startswith=student_data.get('section', '')).first()
                    if section_obj:
                        section_details = self.exam.section_details.filter(section=section_obj).first()
                        if section_details:
                            exam_subjects = section_details.exam_subjects.all()
                            self.errors.append(f"İş nömrəsi {student_data.get('work_number', 'N/A')}: {exam_subjects.count()} fənn üçün bal hesablanması uğursuz oldu")
                except Exception as subject_info_error:
                    self.errors.append(f"İş nömrəsi {student_data.get('work_number', 'N/A')}: Fənn məlumatları da əldə edilə bilmədi - {str(subject_info_error)}")
        else:
            # Section not found, set scores to null
            self.errors.append(f"İş nömrəsi {student_data.get('work_number', 'N/A')}: Bölmə tapılmadığı üçün ballar null olaraq təyin edildi - tələbə yaradılacaq.")
            
        # Apply exam-specific scoring formulas with error handling - only if we have valid scores
        if total_score is not None and subject_results:
            try:
                if self.exam.type == '9-cu sinif buraxılış' and len(subject_results) >= 3:
                    try:
                        subject_results[0]['score'] = (subject_results[0]['score'] * 100) / 30
                        subject_results[1]['score'] = (subject_results[1]['score'] * 100) / 34
                        subject_results[2]['score'] = (subject_results[2]['score'] * 100) / 29
                        total_score = subject_results[0]['score'] + subject_results[1]['score'] + subject_results[2]['score']
                    except Exception as ninth_grade_error:
                        self.errors.append(f"9-cu sinif bal hesablanarkən xəta: {str(ninth_grade_error)}")
                        total_score = None
                        
                elif self.exam.type == '10-cu sinif buraxılış' and len(subject_results) >= 3:
                        try:
                            subject_results[0]['score'] = (subject_results[0]['score'] * 100) / 30
                            subject_results[1]['score'] = (subject_results[1]['score'] * 5) / 2
                            subject_results[2]['score'] = (subject_results[2]['score'] * 25) / 8
                            total_score = subject_results[0]['score'] + subject_results[1]['score'] + subject_results[2]['score']
                        except Exception as tenth_grade_error:
                            self.errors.append(f"10-cu sinif bal hesablanarkən xəta: {str(tenth_grade_error)}")
                            total_score = None
                    
                        
                elif self.exam.type == '11-ci sinif buraxılış' and len(subject_results) >= 3:
                    try:
                        subject_results[0]['score'] = (subject_results[0]['score'] * 100) / 37
                        subject_results[1]['score'] = (subject_results[1]['score'] * 5) / 2
                        subject_results[2]['score'] = (subject_results[2]['score'] * 25) / 8
                        total_score = subject_results[0]['score'] + subject_results[1]['score'] + subject_results[2]['score']
                    except Exception as eleventh_grade_error:
                        self.errors.append(f"11-ci sinif bal hesablanarkən xəta: {str(eleventh_grade_error)}")
                        total_score = None
                        
                elif self.exam.type == "Blok imtahanı":
                    try:
                        total_score = Decimal('0')
                        for subject in range(len(subject_results)):
                            try:
                                subject_qapali_score = Decimal('0')
                                subject_aciq_score = Decimal('0')
                                
                                if 'subject_data' in subject_results[subject] and subject_results[subject]['subject_data']:
                                    for question in range(len(subject_results[subject]['subject_data'])):
                                        try:
                                            question_data = subject_results[subject]['subject_data'][question]
                                            question_type = question_data.get('question_type', '')
                                            question_score = Decimal(str(question_data.get('question_score', '0')))
                                            
                                            if question_type not in ["open", "open_coded", "matching"]:
                                                subject_qapali_score += question_score
                                            else:
                                                subject_aciq_score += question_score
                                        except Exception as question_error:
                                            self.errors.append(f"Blok imtahanı sual {question} hesablanarkən xəta: {str(question_error)}")
                                            
                                if subject_qapali_score < Decimal('0'):
                                    subject_qapali_score = Decimal('0')
                                    
                                subject_score = subject_qapali_score + subject_aciq_score
                                subject_results[subject]['score'] = round(subject_score * 100 / 33, 1)
                                total_score += subject_results[subject]['score']
                            except Exception as subject_error:
                                self.errors.append(f"Blok imtahanı fənn {subject} hesablanarkən xəta: {str(subject_error)}")
                                
                    except Exception as block_exam_error:
                        self.errors.append(f"Blok imtahanı ümumi bal hesablanarkən xəta: {str(block_exam_error)}")
                        total_score = None
                        
                elif self.exam.type == 'Azərbaycan dili (dövlət dili kimi)' and len(subject_results) >= 1:
                    try:
                        total_score = subject_results[0]['score'] * Decimal('10') / Decimal('3')
                        subject_results[0]['score'] = round(subject_results[0]['score'] * Decimal('10') / Decimal('3'), 1)
                    except Exception as azerbaijani_error:
                        self.errors.append(f"Azərbaycan dili bal hesablanarkən xəta: {str(azerbaijani_error)}")
                        total_score = None
                        
            except Exception as scoring_error:
                self.errors.append(f"Imtahan növü üzrə bal hesablanarkən ümumi xəta: {str(scoring_error)}")
                total_score = None
            


        # Finalize student result with error handling
        try:
            # Handle total score - can be null if calculation failed
            if total_score is not None:
                if total_score < 0:
                    total_score = Decimal('0')
                total_score = round(total_score, 1)
            
            student_result.total_score = total_score  # Can be None
            if additional_data:
                student_result.additional_datas = additional_data
                
            student_result.save()
        except Exception as save_error:
            self.errors.append(f"Tələbə nəticəsi saxlanılarkən xəta: {str(save_error)}")
            
        # Create subject results with error handling - continue even if individual subjects fail
        created_subjects_count = 0
        try:
            if subject_results:  # Only create if we have subject results
                for i, subject_data in enumerate(subject_results):
                    try:
                        SubjectResult.objects.create(
                            student_result=student_result,
                            subject_id=subject_data.get('subject_id', 0),
                            total_questions=subject_data.get('total_questions', 0),
                            correct_answers=subject_data.get('correct_answers', 0),
                            wrong_answers=subject_data.get('wrong_answers', 0),
                            empty_answers=subject_data.get('empty_answers', 0),
                            score=subject_data.get('score', None),  # Can be None
                            percentage=subject_data.get('percentage', None),  # Can be None
                            subject_data=subject_data.get('subject_data', [])
                        )
                        created_subjects_count += 1
                    except Exception as subject_save_error:
                        self.errors.append(f"İş nömrəsi {student_data.get('work_number', 'N/A')}: Fənn nəticəsi {i + 1} saxlanarkən xəta: {str(subject_save_error)} - digər fənlər davam edir")
                        continue
                        

            else:
                # No subject results to create (section not found or score calculation failed)
                self.errors.append(f"İş nömrəsi {student_data.get('work_number', 'N/A')}: Fənn nəticələri yaradılmadı (bölmə tapılmadı və ya bal hesablanmadı) - tələbə əsas məlumatları saxlanıldı.")
                    
        except Exception as subject_results_error:
            self.errors.append(f"İş nömrəsi {student_data.get('work_number', 'N/A')}: Fənn nəticələri saxlanarkən kritik xəta: {str(subject_results_error)} - tələbə əsas məlumatları saxlanıldı")

        return student_result

    def _calculate_scores(self, student_data: Dict) -> Tuple[Decimal, List[Dict]]:
        """Calculate total score and subject scores"""
        try:
            # Get correct answers key with error handling
            answers_key = None
            try:
                answers_key = self._get_answers_key(student_data)
            except Exception as key_error:
                raise ValueError(f"Cavab açarı yaradılarkən xəta: {str(key_error)}")
                
            correct_answers = self.correct_answers.get(answers_key, {})
            if not correct_answers:
                available_keys = list(self.correct_answers.keys())
                # Try to find a similar key as fallback
                fallback_key = None
                section_char = answers_key.split('_')[0] if '_' in answers_key else answers_key[0]

                self.errors.append(f"İş nömrəsi {student_data.get('work_number', 'N/A')}: Bu parametrlər üçün düzgün cavablar tapılmadı: {answers_key}.")
                raise ValueError(f"Cavab açarı tapılmadı: {answers_key}")
        except Exception as e:
            self.errors.append(f"İş nömrəsi {student_data.get('work_number', 'N/A')}: Cavab məlumatları yüklənərkən xəta: {str(e)}")
            raise ValueError(f"Cavab məlumatları xətası: {str(e)}")

        total_score = Decimal('0')
        subject_results = []
        additional_data = []
        
        # Get exam structure for subjects with error handling
        section_details = None
        try:
            if self.exam.type == "Blok imtahanı" and 'group' in student_data and student_data['group']:
                try:
                    # First try to find section details for this specific group
                    section_details = self.exam.section_details.filter(
                        section__name__startswith=student_data['section'],
                        group__name=student_data['group']
                    ).first()
                    
                    # If not found, try by group_name field
                    if not section_details:
                        section_details = self.exam.section_details.filter(
                            section__name__startswith=student_data['section'],
                            group_name=student_data['group']
                        ).first()
                    
                    # If still not found, try without group filter (fallback)
                    if not section_details:
                        section_details = self.exam.section_details.filter(
                            section__name__startswith=student_data['section']
                        ).first()
                        if section_details:
                            print(f"WARNING: Using fallback section_details for group '{student_data['group']}'")
                except Exception as block_section_error:
                    raise ValueError(f"Blok imtahanı bölmə detalları axtarılarkən xəta: {str(block_section_error)}")
            else:
                try:
                    # For non-block exams, use normal section filtering
                    section_details = self.exam.section_details.filter(
                        section__name__startswith=student_data['section']
                    ).first()
                except Exception as section_error:
                    raise ValueError(f"Bölmə detalları axtarılarkən xəta: {str(section_error)}")
            
            if not section_details:
                # Raise error to stop score calculation but allow student creation with null scores
                self.errors.append(f"Bölmə detalları tapılmadı: {student_data.get('section', 'N/A')}, qrup: {student_data.get('group', 'Yoxdur')}")
                raise ValueError(f"Bölmə detalları tapılmadı")
                
        except Exception as section_details_error:
            self.errors.append(f"Bölmə struktur məlumatları alınarkən xəta: {str(section_details_error)}")
            raise ValueError(f"Bölmə struktur xətası: {str(section_details_error)}")

        print(f"DEBUG: Using section_details with group: {getattr(section_details, 'group_name', 'None')} for student group: {student_data.get('group', 'None')}")

        # Get student's selected foreign language with error handling
        student_foreign_language = ''
        student_foreign_subject = ''
        try:
            student_foreign_language = student_data.get('foreign_language', '').strip()
            student_foreign_subject = student_data.get('foreign_subject', '').strip()
        except Exception as foreign_lang_error:
            print(f"Xarici dil məlumatları alınarkən xəta: {str(foreign_lang_error)}")

        # Filter foreign language answers with error handling
        filtered_answers = correct_answers
        try:
            if self.exam.type not in ['Blok imtahanı']:
                filtered_answers = self._filter_foreign_language_answers(
                    correct_answers, section_details, student_foreign_language, student_foreign_subject
                )
        except Exception as filter_error:
            print(f"Xarici dil cavabları filtrlənərkən xəta: {str(filter_error)}")
            # Continue with unfiltered answers if filtering fails
        
        print(f"\n=== CALCULATE SCORES DEBUG ===")
        print(f"Student: {student_data.get('student_number', 'Unknown')}")
        print(f"Original correct_answers count: {len(correct_answers)}")
        print(f"Filtered answers count: {len(filtered_answers)}")
        print(f"Original keys sample: {list(correct_answers.keys())[:10]}")
        print(f"Filtered keys sample: {list(filtered_answers.keys())[:10]}")

        current_question = 1
        
        # Track if we have any foreign language subjects and if they were all skipped
        has_foreign_language_subjects = False
        all_foreign_language_skipped = True

        try:
            exam_subjects = section_details.exam_subjects.all()
        except Exception as subjects_error:
            self.errors.append(f"İmtahan fənləri alınarkən xəta: {str(subjects_error)}")
            raise ValueError(f"İmtahan fənləri xətası: {str(subjects_error)}")

        # If no exam subjects found, raise error to stop score calculation
        if not exam_subjects.exists():
            self.errors.append(f"Bu bölmə üçün heç bir fənn tapılmadı.")
            raise ValueError(f"Fənn tapılmadı")

        for exam_subject in exam_subjects:
            try:
                print(f"\n--- Processing subject: {exam_subject.subject.name} (ID: {exam_subject.subject.id}) ---")
                print(f"Is foreign language: {exam_subject.subject.is_foreign_language}")
                print(f"Question count: {exam_subject.question_count}")
                print(f"Current question start: {current_question}")
                
                # Check if this is a foreign language subject with error handling
                try:
                    if exam_subject.subject.is_foreign_language:
                        has_foreign_language_subjects = True
                        # Skip this subject if:
                        # 1. Student has selected a foreign language and it doesn't match this subject
                        # 2. Or student has selected a foreign subject and it doesn't match this subject
                        should_skip = False
                        
                        try:
                            if student_foreign_language and not self._is_matching_foreign_language(
                                exam_subject.subject.name, student_foreign_language
                            ):
                                should_skip = True
                            elif student_foreign_subject and not self._is_matching_foreign_language(
                                exam_subject.subject.name, student_foreign_subject
                            ):
                                should_skip = True
                        except Exception as match_error:
                            print(f"Xarici dil uyğunluq yoxlanarkən xəta: {str(match_error)}")
                            should_skip = False  # Continue processing if matching fails
                        
                        if should_skip:
                            # Skip this subject - DON'T increment question counter for skipped foreign language subjects
                            # This prevents question numbering from being offset by skipped subjects
                            continue
                        else:
                            # At least one foreign language subject was not skipped
                            all_foreign_language_skipped = False
                except Exception as foreign_check_error:
                    print(f"Xarici dil fənni yoxlanarkən xəta: {str(foreign_check_error)}")
                    # Continue processing as regular subject
            except Exception as subject_init_error:
                print(f"Fənn işlənməyə hazırlanarkən xəta: {str(subject_init_error)}")
                continue
            try:
                subject_score = Decimal('0')
                subject_data = []
                correct_count = 0
                wrong_count = 0
                empty_count = 0

                # Process questions for this subject with error handling
                try:
                    question_count = exam_subject.question_count
                except Exception:
                    print(f"Fənn sual sayı alınarkən xəta, default 0 istifadə edilir")
                    question_count = 0

                for q in range(question_count):
                    try:
                        question_num = current_question + q
                        student_answer = ''

                        try:
                            # Safely get student answer
                            if question_num <= len(student_data.get('answers', [])):
                                student_answer = student_data['answers'][question_num - 1]
                        except Exception as answer_error:
                            print(f"Tələbə cavabı alınarkən xəta (sual {question_num}): {str(answer_error)}")

                        # Create key with the global question number (same as in _load_correct_answers)
                        answer_key = str(question_num) + '-' + str(exam_subject.subject.id)

                        if answer_key in filtered_answers:
                            try:
                                question_score = self._calculate_question_score(
                                    student_answer,
                                    filtered_answers[answer_key]
                                )

                                # Ensure question_score is never None
                                if question_score is None:
                                    question_score = Decimal('0')

                                subject_score += question_score

                                try:
                                    # Process question result based on type and score
                                    if question_score > Decimal('0') and filtered_answers[answer_key].get('is_starred', False):
                                        correct_count += 1
                                        subject_data.append({
                                            "student_answer": ';'.join(self._parse_choice_answer(student_answer)) if filtered_answers[answer_key].get('question_type') == "matching" else student_answer,
                                            "result": "+",
                                            "question_score": str(question_score),
                                            "correct_answer": "*",
                                            "question_number": filtered_answers[answer_key].get('question_number', question_num),
                                            "question_type": filtered_answers[answer_key].get('question_type', '')
                                        })
                                    elif filtered_answers[answer_key].get('question_type') == 'essay' and self.exam.type == 'Magistratura':
                                        additional_data.append({"Yazı (esse) işindən topladığı bal": str(question_score)})
                                        subject_score = subject_score - question_score
                                        total_score = total_score + question_score
                                    elif question_score > Decimal('0'):
                                        correct_count += 1
                                        subject_data.append({
                                            "student_answer": ';'.join(self._parse_choice_answer(student_answer)) if filtered_answers[answer_key].get('question_type') == "matching" else student_answer,
                                            "result": "+",
                                            "question_score": str(question_score),
                                            "correct_answer": filtered_answers[answer_key].get('correct_answer', ''),
                                            "question_number": question_num,
                                            "question_type": filtered_answers[answer_key].get('question_type', '')
                                        })
                                    elif student_answer.strip():
                                        subject_data.append({
                                            "student_answer": ';'.join(self._parse_choice_answer(student_answer)) if filtered_answers[answer_key].get('question_type') == "matching" else student_answer,
                                            "result": "-",
                                            "question_score": str(question_score),
                                            "correct_answer": filtered_answers[answer_key].get('correct_answer', ''),
                                            "question_number": question_num,
                                            "question_type": filtered_answers[answer_key].get('question_type', '')
                                        })
                                        wrong_count += 1
                                    else:
                                        subject_data.append({
                                            "student_answer": ';'.join(self._parse_choice_answer(student_answer)) if filtered_answers[answer_key].get('question_type') == "matching" else student_answer,
                                            "result": " ",
                                            "question_score": str(question_score),
                                            "correct_answer": filtered_answers[answer_key].get('correct_answer', ''),
                                            "question_number": question_num,
                                            "question_type": filtered_answers[answer_key].get('question_type', '')
                                        })
                                        empty_count += 1
                                        
                                except Exception as result_process_error:
                                    print(f"Sual nəticəsi emal edilərkən xəta (sual {question_num}): {str(result_process_error)}")
                                    # Continue with next question
                                    
                            except Exception as score_calc_error:
                                print(f"Sual balı hesablanarkən xəta (sual {question_num}): {str(score_calc_error)}")
                                # Continue with next question
                                
                    except Exception as question_error:
                        print(f"Sual {q + 1} emal edilərkən xəta: {str(question_error)}")
                        # Continue with next question
                        continue
                        
            except Exception as subject_processing_error:
                print(f"Fənn emal edilərkən ümumi xəta: {str(subject_processing_error)}")
                # Continue with next subject
            try:
                if subject_score < 0:
                    subject_score = Decimal('0')
                total_score += subject_score

                # Calculate percentage with error handling
                max_possible_score = Decimal('0')
                try:
                    # Use global question numbers (current_question offset) so keys match filtered_answers
                    for q in range(exam_subject.question_count):
                        try:
                            global_qnum = current_question + q
                            answer_key = str(global_qnum) + '-' + str(exam_subject.subject.id)
                            if answer_key in filtered_answers:
                                try:
                                    score_value = filtered_answers[answer_key].get('score', '0')
                                    # Safe Decimal conversion (handle commas / odd formats)
                                    try:
                                        max_possible_score += Decimal(str(score_value))
                                    except Exception:
                                        s = str(score_value).replace(' ', '')
                                        if ',' in s and s.count(',') == 1 and s.count('.') > 0:
                                            s = s.replace('.', '')
                                        s = s.replace(',', '.')
                                        if s.count('.') > 1:
                                            parts = s.split('.')
                                            s = ''.join(parts[:-1]) + '.' + parts[-1]
                                        max_possible_score += Decimal(s)
                                except Exception as score_add_error:
                                    print(f"Maksimal bal əlavə edilərkən xəta: {str(score_add_error)}")
                        except Exception as max_score_error:
                            print(f"Maksimal bal hesablanarkən xəta (sual {q}): {str(max_score_error)}")
                except Exception as percentage_calc_error:
                    print(f"Faiz hesablanarkən xəta: {str(percentage_calc_error)}")
                
                # Debug: print subject and max_possible to help verify correctness
                try:
                    print(f"DEBUG SUBJECT {getattr(exam_subject.subject,'id', '?')} - raw_score={subject_score} max_possible={max_possible_score} percentage={percentage}")
                except Exception:
                    pass

                try:
                    percentage = Decimal('0')
                    try:
                        percentage = (subject_score / max_possible_score * 100) if max_possible_score > 0 else 0
                    except Exception as perc_error:
                        percentage = Decimal('0')
                        print(f"Faiz hesablanarkən xəta: {str(perc_error)}")
                except Exception:
                    percentage = Decimal('0')

                try:
                    subject_results.append({
                        'subject_id': getattr(exam_subject.subject, 'id', 0),
                        'total_questions': getattr(exam_subject, 'question_count', 0),
                        'correct_answers': correct_count,
                        'wrong_answers': wrong_count,
                        'empty_answers': empty_count,
                        'score': subject_score,
                        'percentage': percentage,
                        'subject_data': subject_data
                    })
                except Exception as append_error:
                    print(f"Fənn nəticəsi əlavə edilərkən xəta: {str(append_error)}")
                
                try:
                    current_question += exam_subject.question_count
                except Exception as increment_error:
                    print(f"Sual nömrəsi artırılarkən xəta: {str(increment_error)}")
                    current_question += 1  # Fallback increment

            except Exception as finalize_error:
                print(f"Fənn nəticəsi finallaşdırılarkən xəta: {str(finalize_error)}")
                # Continue with next subject
        # Final validation and cleanup with error handling
        try:
            # If there are foreign language subjects and all were skipped, log warning
            if has_foreign_language_subjects and all_foreign_language_skipped:
                try:
                    work_number = student_data.get('work_number', 'N/A')
                    student_name = student_data.get('student_name', 'N/A')
                    contact_number = student_data.get('contact_number', 'N/A')
                    self.errors.append(
                        f"Tələbə {work_number} {student_name} ({contact_number}) bütün xarici dil fənlərini keçdi. Xarici dil boş qaldı."
                    )
                except Exception as warning_error:
                    self.errors.append("Xarici dil xəbərdarlığı yaradılarkən xəta baş verdi.")
                    
            return total_score, subject_results, additional_data
            
        except Exception as return_error:
            self.errors.append(f"Bal hesablanması nəticələndirilməsində xəta: {str(return_error)}")
            # Don't return anything, let the error propagate
            raise

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
          
        }
        
        student_language_upper = student_language.upper()
        subject_name_lower = subject_name.lower();
        
        # If student language is a single character (code), use mapping
        if len(student_language_upper) == 1 and student_language_upper in language_mapping:
            possible_subjects = language_mapping[student_language_upper]
            return any(subj.lower() in subject_name_lower for subj in possible_subjects)
        
        # If student language is a full name, check if it matches subject name
        return student_language.lower() in subject_name_lower or subject_name_lower in student_language.lower()

    def _get_answers_key(self, student_data: Dict) -> str:
        """Generate key for correct answers lookup"""
        try:
            section = None
            try:
                section = Section.objects.get(name__startswith=student_data.get('section', ''))
            except Section.DoesNotExist:
                raise ValueError(f"Bölmə tapılmadı: {student_data.get('section', 'N/A')}")
            except Exception as section_error:
                raise ValueError(f"Bölmə axtarılarkən xəta: {str(section_error)}")
            
            try:
                key = f"{section.name[0]}_{student_data.get('variant', '')}"
                
                if student_data.get('class_level'):
                    class_obj = Class.objects.filter(name=student_data['class_level']).first()
                    if class_obj:
                        key = f"{class_obj.id}_" + key
                if student_data.get('group'):
                    key = f"{student_data['group']}_" + key 
                if student_data.get('category'):
                    key = f"{student_data['category']}_" + key
                    
                return key
            except Exception as key_build_error:
                raise ValueError(f"Cavab açarı yaradılarkən xəta: {str(key_build_error)}")
                
        except Exception as e:
            raise ValueError(f"Cavab açarı yaradılması zamanı ümumi xəta: {str(e)}")

    def _calculate_question_score(self, student_answer: str, correct_data: Dict) -> Decimal:
        """Calculate score for individual question based on question type"""
        try:
            # Safely extract data with defaults
            student_answer = str(student_answer) if student_answer is not None else ''
            correct_answer = correct_data.get('correct_answer', '')
            
            # Safely convert scores to Decimal
            try:
                base_score = Decimal(str(correct_data.get('score', '0')))
            except (ValueError, TypeError):
                base_score = Decimal('0')
                
            try:
                penalty_score = Decimal(str(correct_data.get('penalty_score', '0')))
            except (ValueError, TypeError):
                penalty_score = Decimal('0')
            
            question_type = correct_data.get('question_type', 'closed')
            
            try:
                # Check for * symbol (except for multiple choice questions)
                if '*' in student_answer and question_type not in ['true_false']:
                    return Decimal('0') - penalty_score
                
                # Determine question type and calculate score
                if correct_data.get('is_starred', False):
                    return base_score
                elif question_type == 'close':
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
                    
            except Exception as calc_error:
                print(f"Sual balı hesablanarkən xəta (növ: {question_type}): {str(calc_error)}")
                return Decimal('0')
                
        except Exception as e:
            print(f"Sual balı hesablanması zamanı ümumi xəta: {str(e)}")
            return Decimal('0')

    def _calculate_closed_question_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for closed questions (A,B,C,D,E)"""
        try:
            student_answer = str(student_answer) if student_answer is not None else ''
            correct_answer = str(correct_answer) if correct_answer is not None else ''
            
            if student_answer.upper() == correct_answer.upper():
                return base_score
            elif student_answer.strip():
                return Decimal('0') - penalty_score
            else:
                return Decimal('0')
        except Exception as e:
            print(f"Qapalı sual balı hesablanarkən xəta: {str(e)}")
            return Decimal('0')
    def _calculate_essay_question_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for essay questions (e.g., 134,21)"""
        try:
            student_answer = str(student_answer).strip() if student_answer is not None else ''
            correct_answer = str(correct_answer).strip() if correct_answer is not None else ''
            
            try:
                if student_answer:
                    # Convert student answer to decimal and multiply by base score
                    return Decimal(str(float(student_answer))) * base_score
                else:
                    return Decimal('0')
            except (ValueError, TypeError) as conversion_error:
                print(f"Esse bal çevrilməsi xətası: {str(conversion_error)}")
                return Decimal('0')
        except Exception as e:
            print(f"Esse sual balı hesablanarkən xəta: {str(e)}")
            return Decimal('0')

    def _calculate_open_question_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for open questions (134,21)"""
        try:
            student_answer = str(student_answer).strip() if student_answer is not None else ''
            correct_answer = str(correct_answer).strip() if correct_answer is not None else ''
            
            if student_answer == correct_answer:
                return base_score
            elif student_answer:
                return Decimal('0') - penalty_score
            else:
                return Decimal('0')
        except Exception as e:
            print(f"Açıq sual balı hesablanarkən xəta: {str(e)}")
            return Decimal('0')

    def _calculate_explained_open_score(self, student_answer: str, correct_answer: str, base_score: Decimal) -> Decimal:
        """Calculate score for explained open questions (1,1/3,2/3,1/2,0)"""
        try:
            student_answer = str(student_answer).strip() if student_answer is not None else ''
            
            if not student_answer:
                return Decimal('0')
            
            # Parse fraction or decimal
            try:
                if '/' in student_answer:
                    parts = student_answer.split('/')
                    if len(parts) == 2:
                        try:
                            answer_value = Decimal(parts[0]) / Decimal(parts[1])
                        except (ValueError, ZeroDivisionError) as fraction_error:
                            print(f"Kəsr cavab analiz xətası: {str(fraction_error)}")
                            return Decimal('0')
                    else:
                        return Decimal('0')
                else:
                    try:
                        answer_value = Decimal(student_answer)
                    except ValueError as decimal_error:
                        print(f"Ondalık cavab analiz xətası: {str(decimal_error)}")
                        return Decimal('0')
                
                return base_score * answer_value
            except Exception as parse_error:
                print(f"İzahlı açıq sual analiz xətası: {str(parse_error)}")
                return Decimal('0')
        except Exception as e:
            print(f"İzahlı açıq sual balı hesablanarkən xəta: {str(e)}")
            return Decimal('0')

    def _calculate_choice_question_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for choice questions (1-ac,2-bd,3-e)"""
        try:
            # Parse student answer from 15-character format
            parsed_student = self._parse_choice_answer(student_answer)
            
            try:
                correct_choices = correct_answer.split(';') if correct_answer else []
            except Exception as split_error:
                print(f"Düzgün seçim cavabı analiz xətası: {str(split_error)}")
                correct_choices = []
            
            if parsed_student == correct_choices:
                return base_score
            elif any(parsed_student):
                return Decimal('0') - penalty_score
            else:
                return Decimal('0')
        except Exception as e:
            print(f"Seçim sualı balı hesablanarkən xəta: {str(e)}")
            return Decimal('0')

    def _parse_choice_answer(self, answer: str) -> List[str]:
        """Parse choice answer from 15-character format"""
        try:
            if not answer or len(answer) != 15:
                return []
            if answer.strip() == '':
                return []
            
            choices = []
            try:
                for i in range(0, 15, 5):
                    try:
                        choice = answer[i:i+5].strip().replace(' ', '')
                        choices.append(choice.lower())
                    except Exception as choice_error:
                        choices.append('')  # Add empty choice if parsing fails
                        
            except Exception as loop_error:
                print(f"Seçim cavabı analiz edilərkən xəta: {str(loop_error)}")
                return []
            
            return choices
            
        except Exception as e:
            print(f"Seçim cavabı analiz edilməsi zamanı ümumi xəta: {str(e)}")
            return []

    def _calculate_multiple_choice_score(self, student_answer: str, correct_answer: str, base_score: Decimal, penalty_score: Decimal) -> Decimal:
        """Calculate score for multiple choice questions (e.g., 134, student selects first, third, and fourth answers)"""
        try:
            student_answer = str(student_answer) if student_answer is not None else ''
            correct_answer = str(correct_answer) if correct_answer is not None else ''
            
            try:
                student_choices = sorted(student_answer.strip())
                correct_choices = sorted(correct_answer.strip())
            except Exception as sort_error:
                print(f"Çox seçimli sual sıralama xətası: {str(sort_error)}")
                return Decimal('0')
            
            if student_choices == correct_choices:
                return base_score

            return Decimal('0') - penalty_score
        except Exception as e:
            print(f"Çox seçimli sual balı hesablanarkən xəta: {str(e)}")
            return Decimal('0')

    from decimal import Decimal

    def _calculate_multiple_alphabet_choice_score(
        self,
        student_answer: str,
        correct_answer: str,
        base_score: Decimal,
        penalty_score: Decimal
    ) -> Decimal:
        """Calculate score for multiple alphabet choice questions (e.g., ABAB)"""
        
        student_choices = list(student_answer.strip().upper())
        correct_choices = list(correct_answer.strip().upper())

        if student_choices == correct_choices:
            return base_score

        # Count position-wise matches
        matches = sum(s == c for s, c in zip(student_choices, correct_choices))

        if matches == len(correct_choices) - 1:
            return Decimal('0.5')
        
        return Decimal('0')

    def recheck_results(self, work_numbers: List[str] = None, branch_filter: str = None) -> Dict:
        """
        Recheck existing student results with updated correct answers from database
        
        Args:
            work_numbers: Optional list of specific work numbers to recheck
            branch_filter: Optional branch filter to limit results
        
        Returns:
            Dictionary with recheck results
        """
        try:
            # Get student results to recheck
            student_results_query = StudentResult.objects.filter(exam=self.exam)
            
            if work_numbers:
                student_results_query = student_results_query.filter(work_number__in=work_numbers)
            
            if branch_filter:
                student_results_query = student_results_query.filter(branch__name__icontains=branch_filter)
            elif self.branch:
                student_results_query = student_results_query.filter(branch=self.branch)
            
            student_results = student_results_query.all()
            
            if not student_results.exists():
                return {
                    'success': False,
                    'error': 'Yenidən yoxlanacaq tələbə nəticələri tapılmaddı',
                    'rechecked_count': 0,
                    'errors': []
                }
            
            rechecked_count = 0
            errors = []
            rechecked_results = []
            
            for student_result in student_results:
                try:
                    # Reconstruct student data from existing result
                    student_data = self._reconstruct_student_data(student_result)
                    
                    # Recalculate scores with current correct answers
                    total_score, subject_results, additional_data = self._calculate_scores(student_data)
                    
                    # Apply exam-specific scoring if needed
                    if self.exam.type == '9-cu sinif buraxılış':
                        if len(subject_results) >= 3:
                            subject_results[0]['score'] = (subject_results[0]['score'] * 100) / 30
                            subject_results[1]['score'] = (subject_results[1]['score'] * 100) / 34
                            subject_results[2]['score'] = (subject_results[2]['score'] * 100) / 29
                            total_score = subject_results[0]['score'] + subject_results[1]['score'] + subject_results[2]['score']
                    
                    elif self.exam.type == '10-cu sinif buraxılış' and len(subject_results) >= 3:
                        try:
                            subject_results[0]['score'] = (subject_results[0]['score'] * 100) / 30
                            subject_results[1]['score'] = (subject_results[1]['score'] * 5) / 2
                            subject_results[2]['score'] = (subject_results[2]['score'] * 25) / 8
                            total_score = subject_results[0]['score'] + subject_results[1]['score'] + subject_results[2]['score']
                        except Exception as tenth_grade_error:
                            self.errors.append(f"10-cu sinif bal hesablanarkən xəta: {str(tenth_grade_error)}")
                            total_score = None
                    
                    elif self.exam.type == '11-ci sinif buraxılış':
                        if len(subject_results) >= 3:
                            subject_results[0]['score'] = (subject_results[0]['score'] * 100) / 37
                            subject_results[1]['score'] = (subject_results[1]['score'] * 5) / 2
                            subject_results[2]['score'] = (subject_results[2]['score'] * 25) / 8
                            total_score = subject_results[0]['score'] + subject_results[1]['score'] + subject_results[2]['score']
                    elif self.exam.type == "Blok imtahanı":
                        total_score = Decimal('0')
                        for subject in range(len(subject_results)):
                            subject_qapali_score = Decimal('0')
                            subject_aciq_score = Decimal('0')
                            for question in range(len(subject_results[subject]['subject_data'])):
                                if subject_results[subject]['subject_data'][question]['question_type'] != "open" and subject_results[subject]['subject_data'][question]['question_type'] != "open_coded" and subject_results[subject]['subject_data'][question]['question_type'] != "matching":
                                    subject_qapali_score += Decimal(subject_results[subject]['subject_data'][question]['question_score'])
                                else:
                                    subject_aciq_score += Decimal(subject_results[subject]['subject_data'][question]['question_score'])
                            if subject_qapali_score < Decimal('0'):
                                subject_qapali_score = Decimal('0')
                            subject_score = subject_qapali_score + subject_aciq_score
                            subject_results[subject]['score'] = round(subject_score*100/33,1)
                            total_score += subject_results[subject]['score']
                    elif self.exam.type == 'Azərbaycan dili (dövlət dili kimi)':
                        total_score = subject_results[0]['score'] * Decimal('10') / Decimal('3')
                        subject_results[0]['score'] = round(subject_results[0]['score'] * Decimal('10') / Decimal('3'), 1)


                    if total_score < 0:
                        total_score = Decimal('0')

                    total_score = round(total_score,1)
                    # Update student result
                    old_total_score = student_result.total_score
                    student_result.total_score = total_score
                    if additional_data:
                        student_result.additional_datas = additional_data
                    student_result.save()
                    
                    # Delete existing subject results and create new ones
                    SubjectResult.objects.filter(student_result=student_result).delete()
                    
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
                    
                    rechecked_results.append({
                        'work_number': student_result.work_number,
                        'student_name': student_result.student_name,
                        'old_score': float(old_total_score) if old_total_score else 0,
                        'new_score': float(total_score),
                        'score_difference': float(total_score) - (float(old_total_score) if old_total_score else 0)
                    })
                    
                    rechecked_count += 1
                    
                except Exception as e:
                    error_msg = f"Tələbə {student_result.work_number} - {student_result.student_name}: {str(e)}"
                    errors.append(error_msg)
                    continue
            
            # Create import log for recheck
            try:
                ImportLog.objects.create(
                    exam=self.exam,
                    branch=self.branch,
                    import_type='recheck',
                    file_name=f'recheck_results_{self.exam.name}_{self.branch.name if self.branch else "all"}.log',
                    file_size=0,
                    records_imported=rechecked_count,
                    errors=errors,
                )
            except Exception as log_error:
                errors.append(f"Import log xətası: {str(log_error)}")
            
            return {
                'success': True,
                'rechecked_count': rechecked_count,
                'errors': errors,
                'results': rechecked_results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Yenidən yoxlama xətası: {str(e)}",
                'rechecked_count': 0,
                'errors': [str(e)]
            }
    
    def _reconstruct_student_data(self, student_result: StudentResult) -> Dict:
        """
        Reconstruct student data from existing StudentResult to reuse scoring logic
        """
        answers = []
        
        # First try to get original answers from stored JSON field
        if hasattr(student_result, 'original_answers') and student_result.original_answers:
            try:
                import json
                answers = json.loads(student_result.original_answers)
            except:
                answers = []
        
        # If no original answers found, reconstruct from subject_data
        if not answers:
            # Get student answers from subject results
            subject_results = SubjectResult.objects.filter(student_result=student_result).order_by('id')
            
            # Reconstruct answers from subject_data in the correct order
            all_question_data = []
            
            for subject_result in subject_results:
                if subject_result.subject_data:
                    for question_data in subject_result.subject_data:
                        if isinstance(question_data, dict) and 'student_answer' in question_data:
                            all_question_data.append(question_data)
            
            # Sort by question_number if available to maintain correct order
            if all_question_data and 'question_number' in all_question_data[0]:
                all_question_data.sort(key=lambda x: x.get('question_number', 0))
            
            # Extract student answers in correct order
            for question_data in all_question_data:
                answers.append(question_data['student_answer'])
        
        # If still no answers found, try to reconstruct from exam structure
        if not answers:
            try:
                section_details = self.exam.section_details.filter(
                    section=student_result.section
                ).first()
                
                if section_details:
                    total_questions = sum(
                        exam_subject.question_count 
                        for exam_subject in section_details.exam_subjects.all()
                    )
                    # Create array of empty answers if we can't reconstruct
                    answers = [''] * total_questions
            except:
                answers = []
        
        # Build student data dictionary
        student_data = {
            'student_name': student_result.student_name,
            'contact_number': student_result.contact_number,
            'work_number': student_result.work_number,
            'gender': student_result.gender or 'K',
            'section': student_result.section.name if student_result.section else '',
            'variant': student_result.variant,
            'answers': answers
        }
        
        # Add optional fields if they exist
        if student_result.class_level:
            student_data['class_level'] = student_result.class_level.name
        
        if student_result.group:
            student_data['group'] = student_result.group.name
        
        # Reconstruct foreign language information from existing subject results
        # This is crucial for proper foreign language filtering during recheck
        foreign_language_detected = None
        foreign_subject_detected = None
        
        # Get all foreign language subjects that exist in the exam
        section_details = self.exam.section_details.filter(
            section=student_result.section
        ).first()
        
        if section_details:
            # Get all foreign language subjects
            foreign_language_subjects = []
            for exam_subject in section_details.exam_subjects.all():
                if exam_subject.subject.is_foreign_language:
                    foreign_language_subjects.append(exam_subject.subject)
            
            # Check which foreign language subject has results for this student
            existing_subject_results = SubjectResult.objects.filter(
                student_result=student_result,
                subject__is_foreign_language=True
            )
            
            if existing_subject_results.exists():
                # Get the foreign language subject that was actually processed
                processed_foreign_subject = existing_subject_results.first().subject
                
                # Map subject name back to language code based on common patterns
                subject_name_lower = processed_foreign_subject.name.lower()
                
                if 'ingilis' in subject_name_lower or 'english' in subject_name_lower:
                    foreign_language_detected = 'I'
                    foreign_subject_detected = 'I'
                elif 'rus' in subject_name_lower or 'russian' in subject_name_lower:
                    foreign_language_detected = 'R'
                    foreign_subject_detected = 'R'
                elif 'fransız' in subject_name_lower or 'french' in subject_name_lower:
                    foreign_language_detected = 'F'
                    foreign_subject_detected = 'F'
                elif 'alman' in subject_name_lower or 'german' in subject_name_lower:
                    foreign_language_detected = 'A'
                    foreign_subject_detected = 'A'
                else:
                    # If we can't determine the code, use the full subject name
                    foreign_language_detected = processed_foreign_subject.name
                    foreign_subject_detected = processed_foreign_subject.name
        
        # Add foreign language information to student data
        if foreign_language_detected:
            student_data['foreign_language'] = foreign_language_detected
        if foreign_subject_detected:
            student_data['foreign_subject'] = foreign_subject_detected
        
        # Try to determine foreign language from exam type or existing data (fallback)
        if not foreign_language_detected and hasattr(student_result, 'foreign_language'):
            student_data['foreign_language'] = getattr(student_result, 'foreign_language', '')
        
        return student_data

    def _filter_foreign_language_answers(self, correct_answers: Dict, section_details, student_foreign_language: str, student_foreign_subject: str) -> Dict:
        """
        Filter correct answers to remove unselected foreign language subjects.
        Keeps only the foreign language subject that matches student's selection.
        Does NOT touch non-foreign language subjects - keeps them all.
        """
        filtered_answers = {}
        
        # Find the selected foreign language subject
        selected_foreign_subject_id = None
        for exam_subject in section_details.exam_subjects.all():
            if exam_subject.subject.is_foreign_language:
                # Check if this is the selected foreign language
                is_selected = False
                
                if student_foreign_language and self._is_matching_foreign_language(
                    exam_subject.subject.name, student_foreign_language
                ):
                    is_selected = True
                elif student_foreign_subject and self._is_matching_foreign_language(
                    exam_subject.subject.name, student_foreign_subject
                ):
                    is_selected = True
                
                if is_selected:
                    selected_foreign_subject_id = exam_subject.subject.id
                    break
        
        # Filter answers - keep ALL non-foreign language subjects and ONLY selected foreign language subject
        for answer_key, answer_data in correct_answers.items():
            subject = answer_data.get('subject')
            if subject:
                # If it's a foreign language subject
                if subject.is_foreign_language:
                    # Only keep if it's the selected foreign language subject
                    if subject.id == selected_foreign_subject_id:
                        filtered_answers[answer_key] = answer_data
                        print(f"Keeping foreign language answer: {answer_key} for subject {subject.name}")
                    else:
                        print(f"Skipping foreign language answer: {answer_key} for subject {subject.name}")
                    # Skip all other foreign language subjects (do not add to filtered_answers)
                else:
                    # Keep ALL non-foreign language subjects unchanged
                    filtered_answers[answer_key] = answer_data
                    print(f"Keeping non-foreign language answer: {answer_key} for subject {subject.name}")
            else:
                # Keep answers without subject info (backward compatibility)
                filtered_answers[answer_key] = answer_data
                print(f"Keeping answer without subject info: {answer_key}")
        
        print(f"Total filtered answers: {len(filtered_answers)}")
        return filtered_answers

    def _parse_fallback(self, line: str) -> Dict:
        """Fallback parser for when specific parsers fail"""
        try:
            parts = line.split(';')
            if len(parts) < 5:
                raise ValueError("Minimum məlumatlar mövcud deyil")
            
            # Try to clean names with error handling
            try:
                parts[0] = parts[0].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
                parts[1] = parts[1].replace('u', 'Ü').replace('o', 'Ö').replace('g', 'Ğ').replace('i', 'İ').replace('e', 'Ə').replace('s', 'Ş').replace('c', 'Ç')
            except Exception:
                pass
            
            # Extract and process class_level
            class_level = parts[7].strip() if len(parts) > 7 else ''
            # Check if class level is "M " (graduate)
            if class_level.upper() == "M" or class_level.upper() == "M ":
                class_level = "Məzun"
                
            return {
                'student_name': f"{parts[0].strip()} {parts[1].strip()}" if len(parts) > 1 else parts[0].strip(),
                'contact_number': parts[2].strip() if len(parts) > 2 else '',
                'gender': parts[3].strip() if len(parts) > 3 else 'K',
                'work_number': parts[4].strip() if len(parts) > 4 else '',
                'section': parts[5].strip() if len(parts) > 5 else 'A',  # Default section
                'variant': parts[6].strip() if len(parts) > 6 else 'A',  # Default variant
                'class_level': class_level,
                'school_number': '',  # Will be mapped later
                'answers': parts[8:] if len(parts) > 8 else []
            }
        except Exception as e:
            raise ValueError(f"Fallback parsing xətası: {str(e)}")

    def _parse_basic(self, line: str) -> Dict:
        """Basic parser for critical error recovery"""
        try:
            parts = line.split(';')
            if len(parts) < 2:
                # Try other delimiters
                for delimiter in [',', '\t', ' ']:
                    test_parts = line.split(delimiter)
                    if len(test_parts) >= 2:
                        parts = test_parts
                        break
                
            if len(parts) < 2:
                raise ValueError("Sətir bölünə bilmədi")
            
            # Extract minimal required info
            student_name = "Naməlum Tələbə"
            work_number = f"BASIC_{abs(hash(line)) % 999999}"
            
            try:
                if len(parts) >= 2:
                    student_name = f"{parts[0].strip()} {parts[1].strip()}"
                elif len(parts) >= 1:
                    student_name = parts[0].strip()
                    
                # Try to find work number in parts
                for i, part in enumerate(parts):
                    if part.strip().isdigit() and len(part.strip()) >= 4:
                        work_number = part.strip()
                        break
                        
            except Exception:
                pass
            
            return {
                'student_name': student_name[:100],  # Limit length
                'contact_number': '',
                'gender': 'K',
                'work_number': work_number[:20],  # Limit length
                'section': 'A',  # Default
                'variant': 'A',  # Default
                'class_level': '',
                'school_number': '',  # Will be mapped later
                'answers': []
            }
        except Exception as e:
            raise ValueError(f"Basic parsing xətası: {str(e)}")

