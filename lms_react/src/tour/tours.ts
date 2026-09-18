import type { UserRole } from '../domain/types';
import { adminTour } from './steps/admin';
import { instructorTour } from './steps/instructor';
import { studentTour } from './steps/student';
import type { TourDefinition } from './types';

export { adminTour, instructorTour, studentTour };

/** 역할에 맞는 이용 안내 투어 */
export function tourFor(role: UserRole): TourDefinition {
  switch (role) {
    case 'admin':
      return adminTour;
    case 'instructor':
      return instructorTour;
    default:
      return studentTour;
  }
}
