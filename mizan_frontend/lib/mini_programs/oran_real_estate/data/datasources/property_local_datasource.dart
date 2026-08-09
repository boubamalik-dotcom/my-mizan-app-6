import '../../domain/entities/property.dart';
import '../../domain/entities/property_amenity.dart';

/// A small catalogue of mid-to-high-end Oran listings, used while
/// `GET /properties` does not exist in `mizan_backend`.
///
/// This is showcase data, not a cache: it exists so the listing screen
/// and its premium filters are usable and reviewable before the
/// property API ships. `PropertyRepository` only reaches for it when
/// the endpoint is absent, and flags the result so the UI can say
/// plainly that the listings are illustrative — nothing here is ever
/// passed off as live inventory.
///
/// The spread of amenities is deliberate: every filter matches some
/// listings and excludes others, and no single listing has all four,
/// so combining chips visibly narrows the results.
class PropertyLocalDataSource {
  const PropertyLocalDataSource();

  List<Property> showcaseCatalogue() {
    return const <Property>[
      Property(
        id: 'oran-001',
        title: 'شقة فاخرة بإطلالة على البحر',
        district: 'الصديقية، وهران',
        price: 42000000,
        currency: 'DZD',
        bedrooms: 4,
        bathrooms: 3,
        areaSqm: 210,
        isFeatured: true,
        amenities: <PropertyAmenity>{
          PropertyAmenity.privatePool,
          PropertyAmenity.highFloor,
          PropertyAmenity.kingBed,
        },
      ),
      Property(
        id: 'oran-002',
        title: 'بنتهاوس بانورامي في قلب المدينة',
        district: 'وسط المدينة، وهران',
        price: 58500000,
        currency: 'DZD',
        bedrooms: 5,
        bathrooms: 4,
        areaSqm: 280,
        isFeatured: true,
        amenities: <PropertyAmenity>{
          PropertyAmenity.highFloor,
          PropertyAmenity.kingBed,
          PropertyAmenity.nonSmoking,
        },
      ),
      Property(
        id: 'oran-003',
        title: 'فيلا عصرية بمسبح خاص',
        district: 'عين الترك، وهران',
        price: 76000000,
        currency: 'DZD',
        bedrooms: 6,
        bathrooms: 5,
        areaSqm: 420,
        amenities: <PropertyAmenity>{
          PropertyAmenity.privatePool,
          PropertyAmenity.nonSmoking,
        },
      ),
      Property(
        id: 'oran-004',
        title: 'شقة راقية قرب الواجهة البحرية',
        district: 'المرسى الكبير، وهران',
        price: 31500000,
        currency: 'DZD',
        bedrooms: 3,
        bathrooms: 2,
        areaSqm: 155,
        amenities: <PropertyAmenity>{
          PropertyAmenity.kingBed,
          PropertyAmenity.nonSmoking,
        },
      ),
      Property(
        id: 'oran-005',
        title: 'دوبلكس واسع بحديقة خاصة',
        district: 'بئر الجير، وهران',
        price: 49000000,
        currency: 'DZD',
        bedrooms: 5,
        bathrooms: 3,
        areaSqm: 320,
        amenities: <PropertyAmenity>{
          PropertyAmenity.privatePool,
          PropertyAmenity.kingBed,
        },
      ),
      Property(
        id: 'oran-006',
        title: 'استوديو أنيق للمستثمرين',
        district: 'حي الصباح، وهران',
        price: 12800000,
        currency: 'DZD',
        bedrooms: 1,
        bathrooms: 1,
        areaSqm: 62,
        amenities: <PropertyAmenity>{PropertyAmenity.nonSmoking},
      ),
    ];
  }
}
