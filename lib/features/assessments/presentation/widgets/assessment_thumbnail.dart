import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../shared/providers/firebase_providers.dart';

/// 성취도평가 썸네일 — Storage getData + 다운스케일로 웹 GPU 부담 완화
class AssessmentThumbnail extends ConsumerStatefulWidget {
  const AssessmentThumbnail({
    super.key,
    this.url,
    this.storagePath,
    this.bytes,
    this.title,
    this.width = 96,
    this.height = 72,
    this.borderRadius = 8,
    this.placeholderIcon = Icons.quiz_outlined,
    this.placeholderIconSize = 28,
  });

  final String? url;
  final String? storagePath;
  final Uint8List? bytes;
  final String? title;
  final double width;
  final double height;
  final double borderRadius;
  final IconData placeholderIcon;
  final double placeholderIconSize;

  static final Map<String, Uint8List> _cache = {};

  static void putCache(String key, Uint8List bytes) {
    if (key.isEmpty || bytes.isEmpty) return;
    _cache[key] = bytes;
  }

  static String? pathFromDownloadUrl(String url) {
    final uri = Uri.tryParse(url.trim());
    if (uri == null) return null;
    final segments = uri.pathSegments;
    final o = segments.indexOf('o');
    if (o < 0 || o + 1 >= segments.length) return null;
    return Uri.decodeComponent(segments[o + 1]);
  }

  /// 목록용으로 작게 디코드 — CanvasKit context lost 완화
  static Future<Uint8List> downscaleForThumb(
    Uint8List raw, {
    int maxWidth = 192,
    int maxHeight = 144,
  }) async {
    try {
      final codec = await ui.instantiateImageCodec(
        raw,
        targetWidth: maxWidth,
        targetHeight: maxHeight,
      );
      final frame = await codec.getNextFrame();
      final data = await frame.image.toByteData(format: ui.ImageByteFormat.png);
      frame.image.dispose();
      if (data == null) return raw;
      return data.buffer.asUint8List();
    } catch (_) {
      return raw;
    }
  }

  @override
  ConsumerState<AssessmentThumbnail> createState() =>
      _AssessmentThumbnailState();
}

class _AssessmentThumbnailState extends ConsumerState<AssessmentThumbnail> {
  Uint8List? _loaded;
  var _loading = false;
  var _failed = false;
  String? _loadKey;

  @override
  void initState() {
    super.initState();
    _hydrateFromCache();
    _scheduleLoad();
  }

  @override
  void didUpdateWidget(covariant AssessmentThumbnail oldWidget) {
    super.didUpdateWidget(oldWidget);
    final oldKey = _cacheKeyFor(
      path: oldWidget.storagePath,
      url: oldWidget.url,
    );
    final newKey = _cacheKey();
    if (oldKey == newKey && oldWidget.bytes == widget.bytes) return;
    _failed = false;
    _hydrateFromCache();
    _scheduleLoad();
  }

  void _hydrateFromCache() {
    final memory = widget.bytes;
    if (memory != null && memory.isNotEmpty) {
      _loaded = memory;
      return;
    }
    final key = _cacheKey();
    if (key == null) {
      _loaded = null;
      return;
    }
    final cached = AssessmentThumbnail._cache[key];
    if (cached != null) _loaded = cached;
  }

  void _scheduleLoad() {
    if (widget.bytes != null && widget.bytes!.isNotEmpty) return;
    final key = _cacheKey();
    if (key == null) return;
    if (AssessmentThumbnail._cache.containsKey(key)) {
      _loaded = AssessmentThumbnail._cache[key];
      return;
    }
    if (_loading && _loadKey == key) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _loadBytes(key);
    });
  }

  String? _cacheKey() => _cacheKeyFor(
    path: widget.storagePath,
    url: widget.url,
  );

  String? _cacheKeyFor({String? path, String? url}) {
    final p = path?.trim();
    if (p != null && p.isNotEmpty && !p.startsWith('demo://')) return p;
    final u = url?.trim();
    if (u != null && u.isNotEmpty) {
      final fromUrl = AssessmentThumbnail.pathFromDownloadUrl(u);
      if (fromUrl != null && fromUrl.isNotEmpty) return fromUrl;
      return u;
    }
    return null;
  }

  String? _effectivePath() {
    final path = widget.storagePath?.trim();
    if (path != null && path.isNotEmpty && !path.startsWith('demo://')) {
      return path;
    }
    final url = widget.url?.trim();
    if (url != null && url.startsWith('http')) {
      return AssessmentThumbnail.pathFromDownloadUrl(url);
    }
    return null;
  }

  Future<void> _loadBytes(String key) async {
    if (_loading && _loadKey == key) return;
    if (AssessmentThumbnail._cache.containsKey(key)) {
      if (mounted) {
        setState(() {
          _loaded = AssessmentThumbnail._cache[key];
          _failed = false;
        });
      }
      return;
    }

    _loading = true;
    _loadKey = key;
    try {
      final storage = ref.read(firebaseStorageProvider);
      Uint8List? data;
      final path = _effectivePath();

      if (path != null) {
        try {
          data = await storage.ref(path).getData(5 * 1024 * 1024);
        } catch (_) {}
      }

      final url = widget.url?.trim();
      if ((data == null || data.isEmpty) &&
          url != null &&
          url.isNotEmpty &&
          (url.startsWith('http://') || url.startsWith('https://'))) {
        try {
          data = await storage.refFromURL(url).getData(5 * 1024 * 1024);
        } catch (_) {}
      }

      if (!mounted || _loadKey != key) return;

      if (data != null && data.isNotEmpty) {
        final scaled = kIsWeb
            ? await AssessmentThumbnail.downscaleForThumb(data)
            : data;
        AssessmentThumbnail.putCache(key, scaled);
        final pathKey = _effectivePath();
        if (pathKey != null && pathKey != key) {
          AssessmentThumbnail.putCache(pathKey, scaled);
        }
        if (url != null && url.isNotEmpty && url != key) {
          AssessmentThumbnail.putCache(url, scaled);
        }
        if (!mounted || _loadKey != key) return;
        setState(() {
          _loaded = scaled;
          _failed = false;
        });
      } else {
        setState(() => _failed = true);
      }
    } finally {
      _loading = false;
    }
  }

  Color _tintForTitle(String title) {
    final palette = [
      AppColors.tint(const Color(0xFFDBEAFE)),
      AppColors.tint(const Color(0xFFD1FAE5)),
      AppColors.tint(const Color(0xFFEDE9FE)),
      AppColors.tint(const Color(0xFFFFE4E6)),
      AppColors.tint(const Color(0xFFFEF3C7)),
      AppColors.tint(const Color(0xFFCCFBF1)),
      AppColors.tint(const Color(0xFFE0E7FF)),
    ];
    if (title.isEmpty) return palette[0];
    return palette[title.hashCode.abs() % palette.length];
  }

  Color _fgForTitle(String title) {
    const palette = [
      Color(0xFF1D4ED8),
      Color(0xFF047857),
      Color(0xFF6D28D9),
      Color(0xFFBE123C),
      Color(0xFFB45309),
      Color(0xFF0F766E),
      Color(0xFF3730A3),
    ];
    if (title.isEmpty) return palette[0];
    return palette[title.hashCode.abs() % palette.length];
  }

  Widget _placeholder() {
    final title = widget.title?.trim() ?? '';
    final initial = title.isNotEmpty ? title.characters.first : null;
    return Container(
      width: widget.width,
      height: widget.height,
      color: title.isNotEmpty
          ? _tintForTitle(title)
          : AppColors.tint(const Color(0xFFF3F4F6)),
      alignment: Alignment.center,
      child: initial != null
          ? Text(
              initial,
              style: TextStyle(
                fontSize: widget.placeholderIconSize,
                fontWeight: FontWeight.w800,
                color: _fgForTitle(title),
              ),
            )
          : Icon(
              widget.placeholderIcon,
              size: widget.placeholderIconSize,
              color: AppColors.textHint,
            ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final memory = widget.bytes;
    final bytes = (memory != null && memory.isNotEmpty) ? memory : _loaded;
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final decodeW = (widget.width * dpr).round().clamp(64, 256);
    final decodeH = (widget.height * dpr).round().clamp(48, 192);

    return ClipRRect(
      borderRadius: BorderRadius.circular(widget.borderRadius),
      child: SizedBox(
        width: widget.width,
        height: widget.height,
        child: bytes != null
            ? Image(
                image: ResizeImage(
                  MemoryImage(bytes),
                  width: decodeW,
                  height: decodeH,
                  allowUpscaling: false,
                ),
                fit: BoxFit.cover,
                width: widget.width,
                height: widget.height,
                gaplessPlayback: true,
                errorBuilder: (_, __, ___) => _placeholder(),
              )
            : (!_failed && !kIsWeb && (widget.url?.startsWith('http') ?? false))
            ? Image.network(
                widget.url!.trim(),
                fit: BoxFit.cover,
                width: widget.width,
                height: widget.height,
                gaplessPlayback: true,
                errorBuilder: (_, __, ___) => _placeholder(),
                frameBuilder: (context, child, frame, wasSynchronouslyLoaded) {
                  if (wasSynchronouslyLoaded || frame != null) {
                    return child;
                  }
                  return _placeholder();
                },
              )
            : _placeholder(),
      ),
    );
  }
}
