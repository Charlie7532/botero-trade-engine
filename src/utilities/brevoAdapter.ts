import axios from 'axios';
import { EmailAdapter, SendEmailOptions } from 'payload';

const brevoAdapter = (): EmailAdapter => {
    const adapter = () => ({
        name: "brevo",
        defaultFromName: process.env.BREVO_SENDER_NAME as string || 'Main 12' as string,
        defaultFromAddress: process.env.BREVO_SENDER_EMAIL as string || 'info@main12.com',
        sendEmail: async (message: SendEmailOptions): Promise<unknown> => {
            if (!process.env.BREVO_EMAILS_ACTIVE) {
                console.log('Brevo emails are not active');
                console.log('Message:', message);
                return;
            }
            try {
                const res = await axios({
                    method: 'POST',
                    url: 'https://api.brevo.com/v3/smtp/email',
                    headers: {
                        'api-key': process.env.BREVO_API_KEY as string,
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                    },
                    data: {
                        sender: {
                            name: process.env.BREVO_SENDER_NAME || 'main12',
                            email: process.env.BREVO_SENDER_EMAIL || 'info@main12.com'
                        },
                        to: [{ email: message.to }],
                        subject: message.subject,
                        htmlContent: message.html,
                    }
                });
                return res.data;
            } catch (error) {
                console.error('Error sending email with Brevo:', error);
            }
        }
    })
    return adapter;
}

export default brevoAdapter;