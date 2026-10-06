import unittest

from alpinus_bulk.photo_gallery import absolute_image, extract_image_urls


class GalleryExtractionTests(unittest.TestCase):
    BASE = "https://alpinusgroup.com/coat/3-6-1204"

    def test_image_without_img_path(self):
        self.assertEqual(
            absolute_image("/uploads/product/arbent-large.webp", self.BASE),
            "https://alpinusgroup.com/uploads/product/arbent-large.webp",
        )

    def test_gallery_anchor_and_responsive_sources(self):
        html = """
        <div class="product-gallery">
          <a href="/media/arbent-front.jpg"><img data-src="/media/arbent-thumb.jpg"></a>
          <img srcset="/uploads/arbent-side-400.webp 400w, /uploads/arbent-side-1600.webp 1600w">
        </div>
        """
        images = extract_image_urls(html, self.BASE)
        self.assertIn("https://alpinusgroup.com/media/arbent-front.jpg", images)
        self.assertIn("https://alpinusgroup.com/media/arbent-thumb.jpg", images)
        self.assertIn("https://alpinusgroup.com/uploads/arbent-side-1600.webp", images)

    def test_lazy_and_schema_images(self):
        html = """
        <img data-original="/files/photo-01.png">
        <script type="application/ld+json">{"@type":"Product","image":["https://cdn.example.com/media/coat.jpg"]}</script>
        """
        images = extract_image_urls(html, self.BASE)
        self.assertIn("https://alpinusgroup.com/files/photo-01.png", images)
        self.assertIn("https://cdn.example.com/media/coat.jpg", images)

    def test_excludes_icons_and_inline_data(self):
        images = extract_image_urls(
            '<img src="data:image/png;base64,AAAA"><img src="/assets/logo.png"><img src="/media/product.webp">',
            self.BASE,
        )
        self.assertEqual(images, ["https://alpinusgroup.com/media/product.webp"])

    def test_deduplicates_urls(self):
        images = extract_image_urls(
            '<img src="/media/arbent.jpg"><img data-original="/media/arbent.jpg">',
            self.BASE,
        )
        self.assertEqual(len(images), 1)

    def test_only_image_candidates(self):
        images = extract_image_urls('<img src="/user/login"><img src="/css/img/spinner.png">', self.BASE)
        self.assertEqual(images, [])


if __name__ == "__main__":
    unittest.main()
