/**
 * Email Translations
 *
 * Contains all translatable text used in email templates.
 * Supports English (en) and Spanish (es).
 */

export type SupportedLanguage = 'en' | 'es'

export interface EmailTranslations {
    // Common
    greeting: string
    footerCopyright: string
    footerTagline: string
    footerContactMessage: string
    footerEmailSentTo: string
    footerSecurityNotice: string

    // OTP Email
    otp: {
        subjectLogin: string
        subjectPasswordReset: string
        preheader: string
        purposeLogin: string
        purposePasswordReset: string
        expiresIn: string
        afterSignIn: string
        ignoreMessage: string
    }

    // Welcome Email
    welcome: {
        subject: string
        preheader: string
        title: string
        greeting: string
        introMessage: string
        introSecure: string
        highlightMessage: string
        ctaButton: string
        helpMessage: string
    }

    // Password Reset Email
    passwordReset: {
        subject: string
        preheader: string
        title: string
        intro: string
        expiresIn: string
        afterVerify: string
        warningTitle: string
        warningMessage: string
    }

    // Password Changed Email
    passwordChanged: {
        subject: string
        preheader: string
        title: string
        message: string
        warningTitle: string
        warningMessage: string
        ctaButton: string
    }
}

const translations: Record<SupportedLanguage, EmailTranslations> = {
    en: {
        greeting: 'Hi',
        footerCopyright: 'All rights reserved.',
        footerTagline: 'Secure ticket marketplace for events in Colombia',
        footerContactMessage: 'If you have any issues, feel free to contact us at',
        footerEmailSentTo: 'This email was sent to',
        footerSecurityNotice: "If you don't recognize this action, please contact us.",

        otp: {
            subjectLogin: 'Your Main 12 verification code',
            subjectPasswordReset: 'Your Main 12 password reset code',
            preheader: 'Your Main 12 verification code is',
            purposeLogin: 'Use this code to sign in to your account:',
            purposePasswordReset: 'Use this code to reset your password:',
            expiresIn: 'This code expires in',
            afterSignIn: 'After signing in, you can optionally set a password for faster access next time.',
            ignoreMessage: "If you didn't request this code, you can safely ignore this email.",
        },

        welcome: {
            subject: 'Welcome to Main 12! 🎉',
            preheader: 'Welcome to Main 12! Start exploring events now.',
            title: 'Welcome to Main 12',
            greeting: 'Hello',
            introMessage: 'We\'re excited to have you in our community.',
            introSecure: 'is here to make your experiences secure, reliable, and exciting. Get ready to discover a new way to enjoy your favorite events.',
            highlightMessage: 'Did you know Main 12 verifies every ticket for your safety? Enjoy your events worry-free!',
            ctaButton: 'Start Exploring Events',
            helpMessage: "Questions? Just reply to this email — we're here to help!",
        },

        passwordReset: {
            subject: 'Reset your Main 12 password',
            preheader: 'Your password reset code is',
            title: 'Reset your password',
            intro: 'We received a request to reset your Main 12 password. Use this code to continue:',
            expiresIn: 'This code expires in',
            afterVerify: "After verifying your identity, you'll be able to create a new password.",
            warningTitle: "Didn't request this?",
            warningMessage:
                "If you didn't request a password reset, please ignore this email or contact our support team if you're concerned.",
        },

        passwordChanged: {
            subject: 'Your Main 12 password has been updated',
            preheader: 'Your Main 12 password has been changed successfully.',
            title: 'Password updated successfully',
            message:
                'Your Main 12 password has been successfully changed. You can now use your new password to sign in.',
            warningTitle: 'Not you?',
            warningMessage:
                "If you didn't make this change, please reset your password immediately and contact our support team.",
            ctaButton: 'Sign In Now',
        },
    },

    es: {
        greeting: 'Hola',
        footerCopyright: 'Todos los derechos reservados.',
        footerTagline: 'Mercado seguro de boletas para eventos en Colombia',
        footerContactMessage: 'Si tienes algún problema, no dudes en contactarnos a',
        footerEmailSentTo: 'Este correo fue enviado a',
        footerSecurityNotice: 'Si no reconoces esta acción, por favor contáctanos.',

        otp: {
            subjectLogin: 'Tu código de verificación de Main 12',
            subjectPasswordReset: 'Tu código para restablecer la contraseña de Main 12',
            preheader: 'Tu código de verificación de Main 12 es',
            purposeLogin:
                'Usa este código para iniciar sesión en tu cuenta:',
            purposePasswordReset: 'Usa este código para restablecer tu contraseña:',
            expiresIn: 'Este código expira en',
            afterSignIn:
                'Después de iniciar sesión, puedes establecer una contraseña para un acceso más rápido la próxima vez.',
            ignoreMessage: 'Si no solicitaste este código, puedes ignorar este correo de forma segura.',
        },

        welcome: {
            subject: '¡Bienvenido a Main 12! 🎉',
            preheader: '¡Bienvenido a Main 12! Comienza a explorar eventos ahora.',
            title: '¡Bienvenido a Main 12',
            greeting: '¡Hola',
            introMessage: 'Estamos emocionados de tenerte en nuestra comunidad.',
            introSecure: 'está aquí para hacer tus experiencias seguras, confiables y emocionantes. Prepárate para descubrir una nueva forma de disfrutar tus eventos favoritos.',
            highlightMessage: '¿Sabías que Main 12 verifica cada entrada para tu seguridad? ¡Disfruta tus eventos sin preocupaciones!',
            ctaButton: 'Comenzar a Explorar Eventos',
            helpMessage: '¿Preguntas? Solo responde a este correo — ¡estamos aquí para ayudarte!',
        },

        passwordReset: {
            subject: 'Restablece tu contraseña de Main 12',
            preheader: 'Tu código para restablecer la contraseña es',
            title: 'Restablece tu contraseña',
            intro:
                'Recibimos una solicitud para restablecer tu contraseña de Main 12. Usa este código para continuar:',
            expiresIn: 'Este código expira en',
            afterVerify: 'Después de verificar tu identidad, podrás crear una nueva contraseña.',
            warningTitle: '¿No lo solicitaste?',
            warningMessage:
                'Si no solicitaste restablecer tu contraseña, ignora este correo o contacta a nuestro equipo de soporte si estás preocupado.',
        },

        passwordChanged: {
            subject: 'Tu contraseña de Main 12 ha sido actualizada',
            preheader: 'Tu contraseña de Main 12 ha sido cambiada exitosamente.',
            title: 'Contraseña actualizada exitosamente',
            message:
                'Tu contraseña de Main 12 ha sido cambiada exitosamente. Ahora puedes usar tu nueva contraseña para iniciar sesión.',
            warningTitle: '¿No fuiste tú?',
            warningMessage:
                'Si no realizaste este cambio, por favor restablece tu contraseña inmediatamente y contacta a nuestro equipo de soporte.',
            ctaButton: 'Iniciar Sesión',
        },
    },
}

/**
 * Get translations for a specific language
 */
export function getEmailTranslations(language: SupportedLanguage = 'en'): EmailTranslations {
    return translations[language] || translations.en
}

export default translations
